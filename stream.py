import cv2
import socket
import struct
import threading
import json
import serial
import time
from queue import Queue

class VideoStreamServer:
    def __init__(self, video_port=8888, control_port=8889, arduino_port='/dev/ttyUSB0'):
        self.video_port = video_port
        self.control_port = control_port
        self.arduino_port = arduino_port
        
        # Initialize camera
        self.camera = cv2.VideoCapture(0)  # USB webcam
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.camera.set(cv2.CAP_PROP_FPS, 30)
        
        # Initialize Arduino serial connection
        try:
            self.arduino = serial.Serial(arduino_port, 9600, timeout=1)
            time.sleep(2)  # Wait for Arduino to initialize
            print(f"Arduino connected on {arduino_port}")
        except Exception as e:
            print(f"Failed to connect to Arduino: {e}")
            self.arduino = None
            
        # Client connections
        self.video_clients = []
        self.control_clients = []
        
        # Threading control
        self.running = False
        
        # Message queue for Arduino responses
        self.arduino_response_queue = Queue()
        
    def start_server(self):
        self.running = True
        
        # Start video server
        video_thread = threading.Thread(target=self.video_server, daemon=True)
        video_thread.start()
        
        # Start control server
        control_thread = threading.Thread(target=self.control_server, daemon=True)
        control_thread.start()
        
        # Start Arduino communication
        if self.arduino:
            arduino_thread = threading.Thread(target=self.arduino_listener, daemon=True)
            arduino_thread.start()
            
        print("Server started successfully")
        print(f"Video port: {self.video_port}")
        print(f"Control port: {self.control_port}")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_server()
            
    def video_server(self):
        video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        video_socket.bind(('0.0.0.0', self.video_port))
        video_socket.listen(5)
        
        print(f"Video server listening on port {self.video_port}")
        
        while self.running:
            try:
                client_socket, addr = video_socket.accept()
                print(f"Video client connected: {addr}")
                
                self.video_clients.append(client_socket)
                
                # Start video streaming thread for this client
                client_thread = threading.Thread(
                    target=self.stream_video_to_client, 
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    print(f"Video server error: {e}")
                    
        video_socket.close()
        
    def control_server(self):
        control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        control_socket.bind(('0.0.0.0', self.control_port))
        control_socket.listen(5)
        
        print(f"Control server listening on port {self.control_port}")
        
        while self.running:
            try:
                client_socket, addr = control_socket.accept()
                print(f"Control client connected: {addr}")
                
                self.control_clients.append(client_socket)
                
                # Start control handler thread for this client
                client_thread = threading.Thread(
                    target=self.handle_control_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    print(f"Control server error: {e}")
                    
        control_socket.close()
        
    def stream_video_to_client(self, client_socket, addr):
        try:
            while self.running:
                ret, frame = self.camera.read()
                if not ret:
                    print("Failed to capture frame")
                    continue
                    
                # Encode frame as JPEG with optimization for low-power Pi
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]  # Reduce quality for Pi
                result, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
                
                if not result:
                    continue
                    
                # Send frame size first
                data = encoded_frame.tobytes()
                size = len(data)
                
                try:
                    client_socket.sendall(struct.pack("!I", size) + data)
                except:
                    # Client disconnected
                    break
                    
                # Control frame rate to reduce Pi load
                time.sleep(1/20)  # ~20 FPS max
                
        except Exception as e:
            print(f"Video streaming error for {addr}: {e}")
        finally:
            if client_socket in self.video_clients:
                self.video_clients.remove(client_socket)
            client_socket.close()
            print(f"Video client {addr} disconnected")
            
    def handle_control_client(self, client_socket, addr):
        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break
                    
                try:
                    message = json.loads(data.decode('utf-8'))
                    self.process_keystroke(message, client_socket)
                except json.JSONDecodeError:
                    print(f"Invalid JSON from {addr}: {data}")
                    
        except Exception as e:
            print(f"Control client error for {addr}: {e}")
        finally:
            if client_socket in self.control_clients:
                self.control_clients.remove(client_socket)
            client_socket.close()
            print(f"Control client {addr} disconnected")
            
    def process_keystroke(self, message, client_socket):
        if not self.arduino:
            return
            
        key_type = message.get('type')
        key = message.get('key')
        
        print(f"Received {key_type}: {key}")
        
        # Format message for Arduino
        arduino_message = f"{key_type}:{key}\n"
        
        try:
            # Send to Arduino
            # self.arduino.write(arduino_message.encode('utf-8'))
            self.arduino.write(f"{arduino_message}\n".encode())
            time.sleep(0.01) # Saftey

            print(f"Sent to Arduino: {arduino_message.strip()}")
            
            # Store client socket for response routing
            self.arduino_response_queue.put(client_socket)
            
        except Exception as e:
            print(f"Arduino communication error: {e}")
            
    def arduino_listener(self):
        """Listen for Arduino responses and forward to clients"""
        while self.running:
            try:
                if self.arduino.in_waiting > 0:
                    response = self.arduino.readline().decode('utf-8').strip()
                    if response:
                        print(f"Arduino response: {response}")

                        # Broadcast to all control clients
                        # Ensure the list is copied to avoid issues if a client disconnects during iteration
                        for client in self.control_clients[:]:
                            try:
                                # Prepend a tag to distinguish Arduino messages
                                tagged_response = f"ARDUINO_MSG:{response}"
                                client.send(tagged_response.encode('utf-8'))
                            except Exception as client_e:
                                print(f"Error sending Arduino response to client: {client_e}. Removing client.")
                                if client in self.control_clients:
                                    self.control_clients.remove(client)

                time.sleep(0.01)  # Small delay to prevent busy waiting

            except Exception as e:
                print(f"Arduino listener error: {e}")
                time.sleep(1)
                
    def stop_server(self):
        print("Stopping server...")
        self.running = False
        
        # Close all client connections
        for client in self.video_clients[:]:
            client.close()
        for client in self.control_clients[:]:
            client.close()
            
        # Close camera
        if self.camera:
            self.camera.release()
            
        # Close Arduino connection
        if self.arduino:
            self.arduino.close()
            
        print("Server stopped")

if __name__ == "__main__":
    # You may need to change the Arduino port based on your setup
    # Common ports: /dev/ttyUSB0, /dev/ttyACM0, /dev/serial0
    server = VideoStreamServer(arduino_port='/dev/ttyUSB0')
    
    try:
        server.start_server()
    except KeyboardInterrupt:
        server.stop_server()