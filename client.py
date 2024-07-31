import socket
import time
import pyautogui
import pickle
import zlib
import uuid
from threading import Thread, Event, Lock
from PIL import Image
import io
import hashlib
import pystray
from pystray import MenuItem as item
import tkinter as tk
from tkinter import messagebox


class ClientConfig:
    """存储客户端配置"""
    SHARED_SECRET_KEY = "my_shared_secret"

    def __init__(self):
        self.username = ''
        self.password = ''
        self.server_ip = ''
        self.server_port = 9999
        self.monitor_frequency = int  # 监控频率，以秒为单位
        self.host_ip = socket.gethostbyname(socket.gethostname())
        self.host_port = int  # 在运行时设置
        self.host_mac = ':'.join(
            ['{:02x}'.format((uuid.getnode() >> elements) & 0xff) for elements in range(0, 2 * 6, 2)][::-1])

    def get_server_ip(self):
        self.server_ip = input("Please tell me the server IP:")

    def get_host_port(self):
        self.host_port = int(input("Please tell me the host port:"))

    def get_frequency(self):
        self.monitor_frequency = int(input("Please tell me the monitor frequency:"))


class ClientNetwork:
    """处理网络连接和数据传输"""

    @staticmethod
    def authenticate_and_send(sock, data, shared_secret_key):
        try:
            auth_request = {'action': 'authenticate', 'key': shared_secret_key}
            ClientNetwork.send_data(sock, auth_request)

            response = ClientNetwork.receive_data(sock)
            if response.get('status') != 'authenticated':
                return False

            # if response.get('data').get('')

            ClientNetwork.send_data(sock, data)
            response = ClientNetwork.receive_data(sock)
            return response
        except Exception as e:
            print(f"Error during sending data: {e}")
            return None

    @staticmethod
    def send_data(sock, data):
        serialized_data = pickle.dumps(data)
        sock.sendall(len(serialized_data).to_bytes(4, 'big') + serialized_data)

    @staticmethod
    def receive_data(sock):
        response_length = int.from_bytes(sock.recv(4), 'big')
        response = sock.recv(response_length)
        response_data = pickle.loads(response)
        print(f"Received data: {response_data}")  # 添加日志，检查接收到的数据
        return response_data

    @staticmethod
    def handle_response(response_data):
        print(f"Handling response: {response_data}")  # 添加日志
        if response_data.get('action') == 'frequency_updated':  # 检查是否是 frequency_updated 响应
            new_frequency = response_data.get('new_frequency')
            if new_frequency:
                client_actions.update_frequency(new_frequency)
                print("Updated frequency successfully")
        elif response_data.get('status') == 'received':
            # 处理接收到的其他类型的响应
            print("Screenshot received successfully")
        elif response_data.get('action') == 'new_port':
            new_port = response_data.get('port')
            if new_port:
                config.server_port = new_port
                print(f"Received new server port: {new_port}")

    @staticmethod
    def connect_and_send(data, config):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((config.server_ip, config.server_port))
                response = ClientNetwork.authenticate_and_send(sock, data, config.SHARED_SECRET_KEY)
                if response:
                    ClientNetwork.handle_response(response)  # 处理响应
                return response
        except Exception as e:
            print(f"Error during sending data: {e}")
            return None


class ClientActions:
    """处理客户端的注册、登录和监控功能"""

    def __init__(self, config):
        self.config = config
        self.stop_event = Event()
        self.monitor_thread = None
        self.frequency_lock = Lock()  # 线程锁

    @staticmethod
    def hash_password(password):
        return hashlib.sha1(password.encode()).hexdigest()

    def register(self):
        try:
            self.config.password = self.hash_password(self.config.password)
            # self.config.host_port = 9999  # 设置客户端监听端口
            response = ClientNetwork.connect_and_send({'action': 'register', 'data': vars(self.config)}, self.config)
            if response and response.get('status') == 'registered':
                print("Client registered successfully.")
                return True
            elif response and response.get('status') == 'already_registered':
                print("Client already registered.")
                return True
            else:
                print("Client registration failed.")
                return False
        except Exception as e:
            print(f"Error during registration: {e}")
            return False

    def login(self):
        try:
            self.config.password = self.hash_password(self.config.password)
            # self.config.host_port = 9999  # 设置客户端监听端口
            response = ClientNetwork.connect_and_send({'action': 'login', 'data': vars(self.config)}, self.config)
            if 'port' in response:
                self.config.server_port = response['port']  # 更新服务器分配的端口号
            if response and response.get('status') == 'registered':
                print("Client logged in successfully.")
                self.start_monitoring()  # 登录成功后启动监控线程
                return True
            else:
                print("Client login failed.")
                return False
        except Exception as e:
            print(f"Error during login: {e}")
            return False

    def update_frequency(self, new_frequency):
        with self.frequency_lock:
            self.config.monitor_frequency = new_frequency
        print(f"Monitor frequency updated to {new_frequency} seconds.")

    def capture_and_send(self):
        while not self.stop_event.is_set():
            try:
                screenshot = pyautogui.screenshot()
                screenshot_bytes = io.BytesIO()
                screenshot.save(screenshot_bytes, format='PNG')
                compressed_screenshot = zlib.compress(screenshot_bytes.getvalue(), level=9)

                data = {
                    'action': 'screenshot',
                    'data': {
                        'mac_address': self.config.host_mac,
                        'username': self.config.username,
                        'screenshot': compressed_screenshot
                    }
                }

                response = ClientNetwork.connect_and_send(data, self.config)
                if response:
                    ClientNetwork.handle_response(response)  # 处理响应

                print(response)
            except Exception as e:
                print(f"Error during screenshot capture and send: {e}")

            with self.frequency_lock:
                current_frequency = self.config.monitor_frequency
                if not isinstance(current_frequency, (int, float)):
                    raise TypeError(
                        f"Expected 'current_frequency' to be an int or float, got {type(current_frequency)}")
            time.sleep(current_frequency)

    def start_monitoring(self):
        self.monitor_thread = Thread(target=self.capture_and_send)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_client(self):
        self.stop_event.set()
        ClientNetwork.connect_and_send({'action': 'disconnect', 'data': {'mac_address': self.config.host_mac}},
                                       self.config)
        if self.monitor_thread:
            self.monitor_thread.join()


class ClientUI(tk.Tk):
    """客户端图形用户界面"""

    def __init__(self, client_actions):
        super().__init__()
        self.client_actions = client_actions
        self.title("Client Interface")
        self.create_widgets()

    def create_widgets(self):
        self.username_label = tk.Label(self, text="Username:")
        self.username_label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)

        self.username_entry = tk.Entry(self)
        self.username_entry.grid(row=0, column=1, padx=10, pady=5)

        self.password_label = tk.Label(self, text="Password:")
        self.password_label.grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)

        self.password_entry = tk.Entry(self, show='*')
        self.password_entry.grid(row=1, column=1, padx=10, pady=5)

        self.register_button = tk.Button(self, text="Register", command=self.register_client)
        self.register_button.grid(row=2, column=0, padx=10, pady=10)

        self.login_button = tk.Button(self, text="Login", command=self.login_client)
        self.login_button.grid(row=2, column=1, padx=10, pady=10)

        self.stop_button = tk.Button(self, text="Stop Client", command=self.stop_client)
        self.stop_button.grid(row=2, column=2, padx=10, pady=10)

        self.minimize_button = tk.Button(self, text="Minimize to Tray", command=self.minimize_to_tray)
        self.minimize_button.grid(row=2, column=3, padx=10, pady=10)

        self.log_text = tk.Text(self, height=15, width=60, wrap='word', padx=10, pady=10, font=('Arial', 12))
        self.log_text.grid(row=3, column=0, columnspan=4, padx=20, pady=20, sticky='nsew')

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(3, weight=1)

    def register_client(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Warning", "Username and password are required.")
            return

        self.client_actions.config.username = username
        self.client_actions.config.password = password

        if self.client_actions.register():
            self.log_text.insert(tk.END, "Client has successfully registered or has already registered.\n")
        else:
            self.log_text.insert(tk.END, "Client registration failed.\n")

    def login_client(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Warning", "Username and password are required.")
            return

        self.client_actions.config.username = username
        self.client_actions.config.password = password

        if self.client_actions.login():
            self.log_text.insert(tk.END, "Client logged in successfully.\n")
        else:
            self.log_text.insert(tk.END, "Client login failed.\n")

    def stop_client(self):
        self.client_actions.stop_client()
        self.log_text.insert(tk.END, "Client stopped.\n")
        self.destroy()

    def minimize_to_tray(self):
        self.withdraw()  # 隐藏窗口


def create_tray_icon(client_ui):
    """创建系统托盘图标"""
    image = Image.open("icon.png")
    menu = (
        item('Restore', client_ui.deiconify),
        item('Quit', client_ui.stop_client),
    )
    tray_icon = pystray.Icon("test_client", image, "Test Client", menu)
    tray_icon.run()


if __name__ == "__main__":
    config = ClientConfig()
    config.get_server_ip()
    config.get_host_port()
    config.get_frequency()
    client_actions = ClientActions(config)
    client_ui = ClientUI(client_actions)

    tray_thread = Thread(target=create_tray_icon, args=(client_ui,))
    tray_thread.daemon = True
    tray_thread.start()

    client_ui.mainloop()

    # 等待监控线程结束
    if client_actions.monitor_thread:
        client_actions.monitor_thread.join()
