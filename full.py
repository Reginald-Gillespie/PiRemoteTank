import cv2
import socket
import struct
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import json
from PIL import Image, ImageTk, ImageEnhance, ImageFilter
import time
import paramiko
import shutil
import scp
from scp import SCPClient
import os
import tempfile
from pathlib import Path

class TankPlantController:
    def __init__(self):
        # --- FIX STARTS HERE ---
        # GUI setup MUST be done first
        self.root = tk.Tk()
        self.root.title("Tank Plant Controller v2.0")
        self.root.geometry("1200x800")

        # Connection settings
        self.server_host = tk.StringVar(value='10.0.0.169')
        self.ssh_password = tk.StringVar(value='pi')
        self.ssh_username = tk.StringVar(value='reginald')
        self.auto_start_python = tk.BooleanVar(value=True)
        self.upload_arduino_code = tk.BooleanVar(value=True)
        self.should_upload_python_code = tk.BooleanVar(value=True)
        self.install_arduino_libraries = tk.BooleanVar(value=True)
        self.install_python = tk.BooleanVar(value=True)
        self.install_python_libraries = tk.BooleanVar(value=True)
        
        # Socket connections
        self.video_socket = None
        self.control_socket = None
        self.running = False
        
        # SSH connection
        self.ssh_client = None
        self.deployment_status = "Disconnected"

        # Video enhancement parameters
        self.brightness = tk.DoubleVar(value=1.0)
        self.contrast = tk.DoubleVar(value=1.2)
        self.sharpness = tk.DoubleVar(value=1.5)

        # --- FIX ENDS HERE ---

        self.setup_gui()
        self.setup_key_bindings()

        # Status tracking
        self.pressed_keys = set()

        # Embedded code content
        # Read python_server_code from file
        python_server_path = Path(__file__).parent / "stream.py"
        with open(python_server_path, "r", encoding="utf-8") as f:
            self.python_server_code = f.read()

    def setup_gui(self):
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Connection Tab
        self.setup_connection_tab(notebook)
        
        # Video Control Tab
        self.setup_video_tab(notebook)

    def setup_connection_tab(self, notebook):
        conn_frame = ttk.Frame(notebook)
        notebook.add(conn_frame, text="Connection & Deployment")

        # Connection settings
        settings_frame = ttk.LabelFrame(conn_frame, text="Connection Settings")
        settings_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(settings_frame, text="Raspberry Pi Host:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        host_entry = ttk.Entry(settings_frame, textvariable=self.server_host, width=20)
        host_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="SSH Username:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        user_entry = ttk.Entry(settings_frame, textvariable=self.ssh_username, width=20)
        user_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="SSH Password:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        pass_entry = ttk.Entry(settings_frame, textvariable=self.ssh_password, show="*", width=20)
        pass_entry.grid(row=2, column=1, padx=5, pady=5)

        upload_check = ttk.Checkbutton(settings_frame, text="Auto Start Python",
                                    variable=self.auto_start_python)
        upload_check.grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        upload_check = ttk.Checkbutton(settings_frame, text="Upload Arduino Code",
                                    variable=self.upload_arduino_code)
        upload_check.grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        
        upload_check = ttk.Checkbutton(settings_frame, text="Install Arduino Libraries",
                                    variable=self.install_arduino_libraries)
        upload_check.grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        upload_check = ttk.Checkbutton(settings_frame, text="Upload Python Code",
                                    variable=self.should_upload_python_code)
        upload_check.grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        upload_check = ttk.Checkbutton(settings_frame, text="Install Python",
                                    variable=self.install_python)
        upload_check.grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        upload_check = ttk.Checkbutton(settings_frame, text="Install Python Libraries",
                                    variable=self.install_python_libraries)
        upload_check.grid(row=8, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        # Deployment controls
        deploy_frame = ttk.LabelFrame(conn_frame, text="Deployment")
        deploy_frame.pack(fill=tk.X, padx=10, pady=10)

        self.deploy_btn = ttk.Button(deploy_frame, text="Deploy & Connect", 
                                   command=self.deploy_and_connect, width=20)
        self.deploy_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.disconnect_btn = ttk.Button(deploy_frame, text="Disconnect", 
                                       command=self.disconnect_all, state=tk.DISABLED, width=20)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Status display
        status_frame = ttk.LabelFrame(conn_frame, text="Deployment Status")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.status_text = tk.Text(status_frame, height=15, wrap=tk.WORD, state=tk.DISABLED)
        status_scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=status_scrollbar.set)

        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        status_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_video_tab(self, notebook):
        video_frame = ttk.Frame(notebook)
        notebook.add(video_frame, text="Video & Control")

        # Video display area
        video_display_frame = ttk.LabelFrame(video_frame, text="Video Stream")
        video_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.video_label = ttk.Label(video_display_frame, text="Connect to start video feed", 
                                   background="black", foreground="white")
        self.video_label.pack(expand=True, fill=tk.BOTH)

        # Enhancement controls
        controls_frame = ttk.LabelFrame(video_frame, text="Video Enhancement")
        controls_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(controls_frame, text="Brightness:").grid(row=0, column=0, sticky=tk.W)
        brightness_scale = ttk.Scale(controls_frame, from_=0.5, to=2.0,
                                   variable=self.brightness, orient=tk.HORIZONTAL, length=200)
        brightness_scale.grid(row=0, column=1, padx=10)

        ttk.Label(controls_frame, text="Contrast:").grid(row=1, column=0, sticky=tk.W)
        contrast_scale = ttk.Scale(controls_frame, from_=0.5, to=3.0,
                                 variable=self.contrast, orient=tk.HORIZONTAL, length=200)
        contrast_scale.grid(row=1, column=1, padx=10)

        ttk.Label(controls_frame, text="Sharpness:").grid(row=2, column=0, sticky=tk.W)
        sharpness_scale = ttk.Scale(controls_frame, from_=0.5, to=3.0,
                                  variable=self.sharpness, orient=tk.HORIZONTAL, length=200)
        sharpness_scale.grid(row=2, column=1, padx=10)

        # Control instructions
        instr_frame = ttk.LabelFrame(controls_frame, text="Controls")
        instr_frame.grid(row=0, column=2, rowspan=3, padx=20, sticky=tk.N)

        instructions = "WASD or Arrow Keys:\nW/↑ - Forward\nS/↓ - Backward\nA/← - Turn Left\nD/→ - Turn Right"
        ttk.Label(instr_frame, text=instructions, justify=tk.LEFT).pack(padx=10, pady=10)

    def setup_key_bindings(self):
        self.root.bind('<KeyPress>', self.on_key_press)
        self.root.bind('<KeyRelease>', self.on_key_release)
        self.root.focus_set()

        def bind_keys_recursive(widget):
            try:
                widget.bind('<KeyPress>', self.on_key_press)
                widget.bind('<KeyRelease>', self.on_key_release)
                for child in widget.winfo_children():
                    bind_keys_recursive(child)
            except:
                pass

        bind_keys_recursive(self.root)

    def log_message(self, message):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def deploy_and_connect(self):
        """Main deployment function"""
        self.deploy_btn.config(state=tk.DISABLED)
        
        # Run deployment in a separate thread to avoid blocking GUI
        deploy_thread = threading.Thread(target=self._deploy_and_connect_thread, daemon=True)
        deploy_thread.start()

    def _deploy_and_connect_thread(self):
        try:
            self.log_message("Starting deployment process...")
            
            # Step 1: Establish SSH connection
            if not self.connect_ssh():
                self.root.after(0, lambda: self.deploy_btn.config(state=tk.NORMAL))
                return

            # Step 2: Upload Python server code
            if self.should_upload_python_code.get():
                self.log_message("Uploading Python server code...")
                if not self.upload_python_code():
                    self.root.after(0, lambda: self.deploy_btn.config(state=tk.NORMAL))
                    return

            # Step 3: Upload and flash Arduino code (if enabled)
            if self.upload_arduino_code.get():
                self.log_message("Uploading Arduino code...")
                if not self.upload_and_flash_arduino():
                    self.root.after(0, lambda: self.deploy_btn.config(state=tk.NORMAL))
                    return

            # Step 4: Start Python server
            if self.auto_start_python.get():
                self.log_message("Starting Python server on Pi...")
                if not self.start_python_server():
                    self.root.after(0, lambda: self.deploy_btn.config(state=tk.NORMAL))
                    return
            else:
                self.log_message("START SERVER MANUALLY IN THE NEXT 2 SECONDS")
                time.sleep(2)

            # Step 5: Connect video and control streams
            self.log_message("Connecting to video and control streams...")
            time.sleep(3)  # Give server time to start
            
            if self.connect_streams():
                self.log_message("Deployment successful! Ready for control.")
                self.root.after(0, lambda: (
                    self.disconnect_btn.config(state=tk.NORMAL),
                    self.deploy_btn.config(state=tk.DISABLED)
                ))
            else:
                self.log_message("Failed to connect to streams")
                self.root.after(0, lambda: self.deploy_btn.config(state=tk.NORMAL))

        except Exception as e:
            self.log_message(f"Deployment failed: {e}")
            self.root.after(0, lambda: self.deploy_btn.config(state=tk.NORMAL))

    def connect_ssh(self):
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.log_message(f"Connecting to {self.server_host.get()}...")
            self.ssh_client.connect(
                hostname=self.server_host.get(),
                username=self.ssh_username.get(),
                password=self.ssh_password.get(),
                timeout=10
            )
            
            self.log_message("SSH connection established")
            return True
            
        except Exception as e:
            self.log_message(f"SSH connection failed: {e}")
            return False

    def upload_python_code(self):
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(self.python_server_code)
                temp_python_path = f.name

            # Upload using SCP
            with scp.SCPClient(self.ssh_client.get_transport()) as scp_client:
                scp_client.put(temp_python_path, '~/tank_server.py')

            # Clean up temp file
            os.unlink(temp_python_path)
            
            self.log_message("Python server code uploaded successfully")
            return True
            
        except Exception as e:
            self.log_message(f"Failed to upload Python code: {e}")
            return False

    def upload_and_flash_arduino(self):
        try:
            # Step 1: Copy the full Arduino project to a temp directory
            local_project_path = os.path.abspath('./ArduinoTankController')
            temp_dir = tempfile.mkdtemp()
            temp_project_path = os.path.join(temp_dir, 'ArduinoTankController')
            shutil.copytree(local_project_path, temp_project_path)

            # Step 2: Create a tarball for transfer
            tar_path = os.path.join(temp_dir, 'ArduinoTankController.tar.gz')
            shutil.make_archive(base_name=tar_path.replace('.tar.gz', ''), format='gztar', root_dir=temp_dir, base_dir='ArduinoTankController')

            # Step 3: Upload tarball
            with SCPClient(self.ssh_client.get_transport()) as scp_client:
                scp_client.put(tar_path, '~/ArduinoTankController.tar.gz')

            # Step 4: Install Arduino CLI if not present
            self.log_message("Checking Arduino CLI installation...")
            stdin, stdout, stderr = self.ssh_client.exec_command('which arduino-cli')
            if stdout.channel.recv_exit_status() != 0:
                self.log_message("Installing Arduino CLI...")
                commands = [
                    'curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh',
                    'sudo mv bin/arduino-cli /usr/local/bin/',
                    'arduino-cli core update-index',
                    'arduino-cli core install arduino:avr'
                ]
                for cmd in commands:
                    stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
                    stdout.channel.recv_exit_status()
                    
            # Step 5: Extract on remote host
            self.log_message("Extracting Arduino project on remote host...")
            cmds = [
                'rm -rf ~/ArduinoTankController',
                'mkdir -p ~/ArduinoTankController',
                'tar -xzf ~/ArduinoTankController.tar.gz -C ~/',
                'rm ~/ArduinoTankController.tar.gz'
            ]
            
            if self.install_arduino_libraries.get():
                cmds.append('arduino-cli lib install "elapsedMillis"')    
                cmds.append('arduino-cli lib install "Adafruit IS31FL3731 Library"')    
                cmds.append('arduino-cli lib install "Servo"')    
            
            # for cmd in cmds:
            #     stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
            #     stdout.channel.recv_exit_status()

            for cmd in cmds:
                self.log_message(f"Executing: {cmd}")
                stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
                exit_status = stdout.channel.recv_exit_status()
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()

                if exit_status != 0:
                    # self.log_message(f"Command failed: {cmd}")
                    if output:
                        self.log_message(f"{output}")
                    if error:
                        self.log_message(f"STDERR: {error}")
                    # You might want to raise an exception or return False here
                else:
                    self.log_message(f"Command successful: {cmd}")
                    if output:
                        self.log_message(f"{output}")


            # Step 6: Find Arduino port
            self.log_message("Detecting Arduino port...")
            stdin, stdout, stderr = self.ssh_client.exec_command('arduino-cli board list')
            board_output = stdout.read().decode()
            arduino_port = None
            for line in board_output.split('\n'):
                if 'Arduino' in line or 'ttyUSB' in line or 'ttyACM' in line:
                    arduino_port = line.split()[0]
                    break
            if not arduino_port:
                for port in ['/dev/ttyUSB0', '/dev/ttyACM0', '/dev/ttyUSB1', '/dev/ttyACM1']:
                    stdin, stdout, stderr = self.ssh_client.exec_command(f'ls {port}')
                    if stdout.channel.recv_exit_status() == 0:
                        arduino_port = port
                        break
            if not arduino_port:
                self.log_message("No Arduino detected. Skipping Arduino upload.")
                return True
            self.log_message(f"Arduino detected on {arduino_port}")

            # Step 7: Compile and upload
            self.log_message("Compiling and uploading Arduino code...")
            compile_cmd = 'arduino-cli compile --fqbn arduino:avr:nano ~/ArduinoTankController --libraries ./ArduinoTankController/libraries'
            upload_cmd = f'arduino-cli upload -p {arduino_port} --fqbn arduino:avr:uno ~/ArduinoTankController'

            stdin, stdout, stderr = self.ssh_client.exec_command(compile_cmd)
            if stdout.channel.recv_exit_status() != 0:
                self.log_message(f"Arduino compile failed: {stderr.read().decode()}")
                return False

            stdin, stdout, stderr = self.ssh_client.exec_command(upload_cmd)
            if stdout.channel.recv_exit_status() != 0:
                self.log_message(f"Arduino upload failed: {stderr.read().decode()}")
                return False

            self.log_message("Arduino code uploaded successfully")
            return True

        except Exception as e:
            self.log_message(f"Arduino upload failed: {e}")
            return False

        finally:
            # Clean up local temp files
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def start_python_server(self):
        try:
            # Kill any existing server
            self.ssh_client.exec_command('pkill -f tank_server.py')
            time.sleep(1)
            
            # Make sure python is installed
            if self.install_python.get():
                self.log_message("Checking Python installation...")
                stdin, stdout, stderr = self.ssh_client.exec_command('which python3')
                if stdout.channel.recv_exit_status() != 0 and self.install_python.get():
                    self.log_message("Installing Python 3...")
                    commands = [
                        'sudo apt-get update -y',
                        'sudo apt-get install -y python3 python3-pip'
                    ]
                    for cmd in commands:
                        self.log_message(f"Executing: {cmd}")
                        stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
                        stdout.channel.recv_exit_status()

            # Install required Python packages
            if self.install_python_libraries.get():
                self.log_message("Installing Python dependencies...")
                install_cmd = 'pip3 install opencv-python pyserial'
                stdin, stdout, stderr = self.ssh_client.exec_command(install_cmd)
                stdout.channel.recv_exit_status()  # Wait for completion

            # Start server in background
            start_cmd = 'cd ~ && python3 tank_server.py > server.log 2>&1 &'
            stdin, stdout, stderr = self.ssh_client.exec_command(start_cmd)
            
            self.log_message("Python server started")
            return True

        except Exception as e:
            self.log_message(f"Failed to start Python server: {e}")
            return False

    def connect_streams(self):
        try:
            # Connect video socket
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.video_socket.settimeout(10)
            self.video_socket.connect((self.server_host.get(), 8888))

            # Connect control socket
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(10)
            self.control_socket.connect((self.server_host.get(), 8889))

            # Remove timeout after successful connection
            self.video_socket.settimeout(None)
            self.control_socket.settimeout(None)

            self.running = True

            # Start video and message threads
            self.video_thread = threading.Thread(target=self.receive_video, daemon=True)
            self.video_thread.start()

            self.message_thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.message_thread.start()

            self.log_message("Connected to video and control streams")
            return True

        except Exception as e:
            self.log_message(f"Stream connection failed: {e}")
            return False

    def disconnect_all(self):
        """Disconnect all connections and stop server"""
        self.running = False

        # Close sockets
        if self.video_socket:
            try:
                self.video_socket.close()
            except:
                pass
        if self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass

        # Stop server on Pi
        if self.ssh_client:
            try:
                self.ssh_client.exec_command('pkill -f tank_server.py')
                self.ssh_client.close()
            except:
                pass

        # Reset GUI
        self.video_label.configure(image='', text="Connect to start video feed")
        self.deploy_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)

        self.log_message("Disconnected from all services")

    def enhance_frame(self, frame):
        """Apply enhancement to video frame for better readability"""
        try:
            # Convert to PIL Image
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            # Apply enhancements
            # Brightness
            enhancer = ImageEnhance.Brightness(pil_image)
            pil_image = enhancer.enhance(self.brightness.get())

            # Contrast
            enhancer = ImageEnhance.Contrast(pil_image)
            pil_image = enhancer.enhance(self.contrast.get())

            # Sharpness
            enhancer = ImageEnhance.Sharpness(pil_image)
            pil_image = enhancer.enhance(self.sharpness.get())

            # Optional: Apply unsharp mask for better text readability
            if self.sharpness.get() > 1.5:
                pil_image = pil_image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))

            return pil_image

        except Exception as e:
            self.log_message(f"Enhancement error: {e}")
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def receive_video(self):
        data = b""
        payload_size = struct.calcsize("!I")

        self.log_message("Starting video reception...")

        while self.running:
            try:
                # Retrieve message size
                while len(data) < payload_size and self.running:
                    try:
                        packet = self.video_socket.recv(4096)
                        if not packet:
                            self.log_message("Video socket closed by server")
                            return
                        data += packet
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.running:
                            self.log_message(f"Error receiving video header: {e}")
                        return

                if len(data) < payload_size:
                    self.log_message("Incomplete video header received")
                    return

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("!I", packed_msg_size)[0]

                # Sanity check for message size
                if msg_size > 1024 * 1024:  # 1MB limit
                    self.log_message(f"Invalid frame size: {msg_size}")
                    data = b""
                    continue

                # Retrieve all data based on message size
                while len(data) < msg_size and self.running:
                    remaining = msg_size - len(data)
                    try:
                        chunk = self.video_socket.recv(min(4096, remaining))
                        if not chunk:
                            self.log_message("Connection lost while receiving frame")
                            return
                        data += chunk
                    except Exception as e:
                        if self.running:
                            self.log_message(f"Error receiving video data: {e}")
                        return

                frame_data = data[:msg_size]
                data = data[msg_size:]

                # Decode frame
                try:
                    frame_array = np.frombuffer(frame_data, dtype=np.uint8)
                    frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)

                    if frame is not None:
                        # Enhance frame
                        enhanced_frame = self.enhance_frame(frame)

                        # Resize for display (maintain aspect ratio)
                        display_width = 640
                        display_height = 480
                        enhanced_frame = enhanced_frame.resize((display_width, display_height), Image.Resampling.LANCZOS)

                        # Convert to PhotoImage
                        photo = ImageTk.PhotoImage(enhanced_frame)

                        # Update GUI in main thread
                        self.root.after(0, self.update_video_display, photo)
                    else:
                        self.log_message("Failed to decode video frame")

                except Exception as e:
                    self.log_message(f"Frame decode error: {e}")

            except Exception as e:
                if self.running:
                    self.log_message(f"Video receive error: {e}")
                break

        self.log_message("Video reception stopped")

    def update_video_display(self, photo):
        self.video_label.configure(image=photo, text='')
        self.video_label.image = photo  # Keep a reference

    def receive_messages(self):
        while self.running:
            try:
                data = self.control_socket.recv(1024)
                if data:
                    message = data.decode('utf-8')
                    # Check if the message is an Arduino message
                    if message.startswith("ARDUINO_MSG:"):
                        arduino_actual_message = message.replace("ARDUINO_MSG:", "").strip()
                        self.log_message(f"Arduino: {arduino_actual_message}")
                    else:
                        # Log other control messages if any, or just ignore if they are not expected to be logged
                        self.log_message(f"Control message: {message}")
            except Exception as e:
                if self.running:
                    self.log_message(f"Message receive error: {e}")
                break

    def on_key_press(self, event):
        # FIX: Allow typing in Entry widgets
        if event.widget.winfo_class() in ('TEntry', 'Entry'):
            return

        if not self.running or not self.control_socket:
            return "break"

        key_name = event.keysym

        # Avoid repeat events for held keys
        if key_name in self.pressed_keys:
            return "break"

        self.pressed_keys.add(key_name)

        try:
            message = json.dumps({"type": "keydown", "key": key_name})
            self.control_socket.send(message.encode('utf-8'))
            self.log_message(f"Key down: {key_name}")
        except Exception as e:
            self.log_message(f"Send error: {e}")

        return "break"

    def on_key_release(self, event):
        if not self.running or not self.control_socket:
            return "break"

        key_name = event.keysym

        if key_name in self.pressed_keys:
            self.pressed_keys.remove(key_name)

        try:
            message = json.dumps({"type": "keyup", "key": key_name})
            self.control_socket.send(message.encode('utf-8'))
            self.log_message(f"Key up: {key_name}")
        except Exception as e:
            self.log_message(f"Send error: {e}")

        return "break"

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.after(100, lambda: self.root.focus_force())
        self.root.mainloop()

    def on_closing(self):
        self.disconnect_all()
        self.root.destroy()

if __name__ == "__main__":
    # Required packages check
    required_packages = ['paramiko', 'scp', 'opencv-python', 'pillow', 'numpy']
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'opencv-python':
                import cv2
            elif package == 'pillow':
                from PIL import Image
            elif package == 'paramiko':
                import paramiko
            elif package == 'scp':
                import scp
            elif package == 'numpy':
                import numpy
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("Missing required packages:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\nInstall them with:")
        print(f"pip install {' '.join(missing_packages)}")
        input("Press Enter to continue anyway...")
    
    controller = TankPlantController()
    controller.run()