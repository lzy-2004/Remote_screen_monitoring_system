import socket
import pickle
import zlib
import threading
from PIL import Image, ImageTk
import io
import os
from datetime import datetime
import tkinter as tk
from pystray import MenuItem as pyMenuItem
import pystray

# 全局变量
SHARED_SECRET_KEY = "my_shared_secret"
screenshot_dir = "screenshots"
user_pass_dir = "user_pass"
client_filename = "client.txt"
new_frequency = ''
response = {}

# 创建截图存储目录和用户存储目录
if not os.path.exists(screenshot_dir):
    os.makedirs(screenshot_dir)

if not os.path.exists(user_pass_dir):
    os.makedirs(user_pass_dir)

if not os.path.exists(client_filename):
    with open(client_filename, 'w') as f:
        pass

registered_users = set()
with open(client_filename, 'r') as f:
    for line in f:
        username = line.strip()
        if username:
            registered_users.add(username)

clients = {}
usernames = {}
server_running = threading.Event()
server_running.set()

# GUI类
class ImageDisplay:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Live Screenshots")
        self.photo_labels = {}
        self.client_windows = {}
        self.client_count = 0

        # Main frame with padding
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        # Status bar
        self.status_bar = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Registered users frame
        registered_users_frame = tk.LabelFrame(self.main_frame, text="Registered Users")
        registered_users_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        self.registered_users_text = tk.Text(registered_users_frame, height=10, width=50, wrap='word', padx=10, pady=10,
                                             font=('Arial', 12))
        self.registered_users_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        for username in registered_users:
            self.registered_users_text.insert(tk.END, username + "\n")

        # Connected users frame
        connected_users_frame = tk.LabelFrame(self.main_frame, text="Connected Users")
        connected_users_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        self.connected_users_text = tk.Text(connected_users_frame, height=10, width=50, wrap='word', padx=10, pady=10,
                                            font=('Arial', 12))
        self.connected_users_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Minimize to tray button
        self.minimize_to_tray_button = tk.Button(self.main_frame, text="Minimize to Tray",
                                                 command=self.minimize_to_tray)
        self.minimize_to_tray_button.pack(pady=10)

        # Client count label
        self.client_count_label = tk.Label(self.main_frame, text=f"Clients connected: {self.client_count}")
        self.client_count_label.pack(pady=10)

        # Frequency frame
        frequency_frame = tk.Frame(self.main_frame)
        frequency_frame.pack(pady=10)
        self.frequency_label = tk.Label(frequency_frame, text="New Frequency (seconds):")
        self.frequency_label.pack(side=tk.LEFT, padx=(0, 10))
        self.frequency_entry = tk.Entry(frequency_frame)
        self.frequency_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.frequency_button = tk.Button(frequency_frame, text="Set Frequency", command=self.set_frequency)
        self.frequency_button.pack(side=tk.LEFT)

        # Add time-based search frame
        search_frame = tk.Frame(self.main_frame)
        search_frame.pack(pady=10)
        self.search_label = tk.Label(search_frame, text="Search by Time (YYYYMMDD_HHMMSS):")
        self.search_label.pack(side=tk.LEFT, padx=(0, 10))
        self.search_entry = tk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.search_username_label = tk.Label(search_frame, text="Username:")
        self.search_username_label.pack(side=tk.LEFT, padx=(0, 10))
        self.search_username_entry = tk.Entry(search_frame)
        self.search_username_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.search_button = tk.Button(search_frame, text="Search", command=self.search_images)
        self.search_button.pack(side=tk.LEFT)

    def clear_connected_users(self):
        self.connected_users_text.delete("1.0", tk.END)
        self.client_count = 0

    def stop_server(self):
        on_quit()
        self.root.destroy()
    def minimize_to_tray(self):
        self.root.withdraw()      # 隐藏主窗口

    def restore_window(self, icon, item):
        self.root.deiconify()  # 恢复窗口显示

    def create_client_button(self, client_data):
        username = client_data['username']
        host_mac = client_data['host_mac']
        button = tk.Button(self.main_frame, text=f"{username} ({host_mac})", command=lambda: self.open_client_window(client_data))
        button.pack(pady=5)
        self.client_windows[host_mac] = button

        self.client_count += 1
        self.client_count_label.config(text=f"Clients connected: {self.client_count}")

        self.update_connected_users(username)

    def open_client_window(self, client_data):
        username = client_data['username']
        host_mac = client_data['host_mac']
        window_title = f"{username} ({host_mac})"
        client_window = tk.Toplevel(self.root)
        client_window.title(window_title)
        photo_label = tk.Label(client_window)
        photo_label.pack()
        self.photo_labels[host_mac] = photo_label

    def update_gui(self, host_mac, image_data, username):
        try:
            image = Image.open(io.BytesIO(image_data))
            image = resize_image(image, 800, 600)
            photo = ImageTk.PhotoImage(image)
            if host_mac in self.photo_labels:
                self.photo_labels[host_mac].config(image=photo)
                self.photo_labels[host_mac].image = photo
                print(f"Image updated successfully for client {username}.")
            else:
                print(f"No window open for client {username}.")
        except Exception as e:
            print(f"Failed to update image for client {username}: {e}")

    def update_registered_users(self, username):
        self.registered_users_text.insert(tk.END, username + "\n")

    def update_connected_users(self, username):
        self.connected_users_text.insert(tk.END, username + "\n")

    def remove_connected_user(self, username):
        content = self.connected_users_text.get("1.0", tk.END)
        updated_content = content.replace(username + "\n", "")
        self.connected_users_text.delete("1.0", tk.END)
        self.connected_users_text.insert("1.0", updated_content)

    def set_frequency(self):
        try:
            new_frequency = int(self.frequency_entry.get())
            self.send_frequency_change_command(new_frequency)
        except ValueError:
            print("Invalid frequency value. Please enter an integer.")


    def send_frequency_change_command(self,new_frequency):
        global response
        for client in clients.values():
            response['action'] = 'frequency_updated'
            response['new_frequency'] = new_frequency
                # serialized_data = pickle.dumps(data)
                # conn.sendall(len(serialized_data).to_bytes(4, 'big') + serialized_data)
                # response_length = int.from_bytes(conn.recv(4), 'big')
                # response = pickle.loads(conn.recv(response_length))
                # print(f"Response from client: {response}")
                # if response.get('status') == 'frequency_updated':
                #     print(f"Client {client['username']} frequency updated to {new_frequency} seconds.")
                # else:
                #     print(f"Failed to update frequency for client {client['username']}.")

    def run(self):
        self.root.mainloop()

    def search_images(self):
        search_time = self.search_entry.get()
        search_username = self.search_username_entry.get().strip()

        if len(search_time) != 15:
            print("Invalid time format. Please enter in the format YYYYMMDD_HHMMSS.")
            return

        found_images = []

        if search_username:
            user_dirs = [search_username] if search_username in registered_users else []
        else:
            user_dirs = registered_users

        for username in user_dirs:
            user_dir = os.path.join(screenshot_dir, username)
            if os.path.exists(user_dir):
                for mac_dir in os.listdir(user_dir):
                    mac_path = os.path.join(user_dir, mac_dir)
                    for image_file in os.listdir(mac_path):
                        if search_time in image_file:
                            found_images.append(os.path.join(mac_path, image_file))

        if found_images:
            self.display_search_results(found_images)
        else:
            print("No images found for the given time.")

    def display_search_results(self, image_paths):
        results_window = tk.Toplevel(self.root)
        results_window.title("Search Results")
        for image_path in image_paths:
            image = Image.open(image_path)
            image = resize_image(image, 800, 600)
            photo = ImageTk.PhotoImage(image)
            label = tk.Label(results_window, image=str(photo))
            label.image = photo  # Keep a reference to avoid garbage collection
            label.pack(pady=5)


def on_quit(icon, item):
    global server_running
    server_running.clear()
    icon.stop()  # 停止托盘图标的显示
    gui_display.root.quit()  # 退出主事件循环


def show_tray_icon(gui_display):
    image = Image.open("taffy.jpg")
    menu = (pyMenuItem('Restore', gui_display.restore_window),
            pyMenuItem('Quit', on_quit))
    icon = pystray.Icon("Live Screenshots", image, "Test_server", menu)
    icon.run()
    icon.visible = True


def resize_image(image, max_width, max_height):
    """
    Resize the image to fit within the specified width and height while maintaining aspect ratio.
    """
    original_width, original_height = image.size
    ratio = min(max_width / original_width, max_height / original_height)
    new_width = int(original_width * ratio)
    new_height = int(original_height * ratio)
    resized_image = image.resize((new_width, new_height), Image.LANCZOS)
    return resized_image


def save_screenshot(client_data, screenshot_data):
    if client_data is None:
        print("Client data is None. Screenshot will not be saved.")
        return

    sanitized_mac = client_data['host_mac'].replace(":", "_")
    user_dir = os.path.join(screenshot_dir, client_data['username'], sanitized_mac)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = os.path.join(user_dir, f"screenshot_{timestamp}.png")

    try:
        image = Image.open(io.BytesIO(screenshot_data))
        image.save(screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")
    except Exception as e:
        print(f"Error saving screenshot: {e}")

def recv_all(conn):
    data = b''
    raw_msglen = conn.recv(4)
    if not raw_msglen:
        return None
    msglen = int.from_bytes(raw_msglen, 'big')
    while len(data) < msglen:
        part = conn.recv(msglen - len(data))
        if not part:
            return None
        data += part
    return data

def handle_register(data, conn, addr, gui_display):
    print(f"Handling register: {data}")
    if 'data' not in data or 'username' not in data['data'] or 'host_mac' not in data['data']:
        print("Invalid register data received")
        return

    mac_address = data['data']['host_mac']
    clients[mac_address] = data['data']
    username = data['data']['username']
    usernames[mac_address] = username
    # Generate a new port number for the client
    # new_port = 10000 + len(clients)  # Starting from port 10000
    # clients[mac_address]['server_port'] = new_port

    if username not in registered_users:
        registered_users.add(username)
        with open(client_filename, 'a') as f:
            f.write(username + "\n")
        gui_display.update_registered_users(username)

        filename = 'user_pass.txt'
        file_path = os.path.join(user_pass_dir, filename)
        content = username + '_' + data['data']['password'] + '$'
        try:
            with open(file_path, 'a') as f:
                f.seek(0, 2)
                f.write(content)
        except IOError:
            print(f"Error writing to file {file_path}")

        response = {'status': 'registered'}
        conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))
        print(f"Client {addr} registered with data: {data['data']}")
    else:
        print("Client has already registered")
        response = {'status': 'already_registered'}
        conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))
def handle_login(data, conn, addr, gui_display):
    print(f"Handling login: {data}")
    if 'data' not in data or 'username' not in data['data'] or 'host_mac' not in data['data']:
        print("Invalid login data received")
        return

    mac_address = data['data']['host_mac']
    username = data['data']['username']
    clients[mac_address] = data['data']
    usernames[mac_address] = username
    userpass = data['data']['username'] + '_' + data['data']['password']
    filename = 'user_pass.txt'
    file_path = os.path.join(user_pass_dir, filename)
    try:
        with open(file_path, 'r') as file:
            content = ''
            while True:
                char = file.read(1)
                if not char:
                    response = {'status': 'notregistered'}
                    conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))
                    break
                if char == '$':
                    if content == userpass:
                        response = {'status': 'registered'}
                        # Generate a new port number for the client
                        new_port = 10000 + len(clients)  # Starting from port 10000
                        clients[mac_address]['server_port'] = new_port
                        response['server_port'] = new_port
                        response['action'] = 'new_port'
                        conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))
                        print(f"Client {addr} registered with data: {data['data']}")
                        gui_display.create_client_button(data['data'])
                        break
                    else:
                        content = ''
                else:
                    content += char

    except IOError:
        print(f"Error: Unable to open file {file_path}")


def handle_screenshot(data, conn, gui_display):
    global response
    print(f"Handling screenshot for {data['data']['username']}")
    if 'data' not in data or 'mac_address' not in data['data'] or 'username' not in data['data'] or 'screenshot' not in data['data']:
        print("Invalid screenshot data received")
        return

    mac_address = data['data']['mac_address']
    username = data['data']['username']
    client_data = clients.get(mac_address)
    if client_data:
        if mac_address not in clients:
            print(f"Ignoring screenshot from disconnected client {username}")
            return

        try:
            screenshot_data = zlib.decompress(data['data']['screenshot'])
            save_screenshot(client_data, screenshot_data)
            response['status'] = 'received'

            conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))
            gui_display.update_gui(mac_address, screenshot_data, username)
        except Exception as e:
            print(f"Error: {e}")
    else:
        print(f"No client data found for MAC address {mac_address}")
        response['status'] = 'client_not_registered'
        conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))


def handle_disconnect(data, conn, gui_display):
    print(f"Handling disconnect: {data}")
    if 'data' not in data or 'mac_address' not in data['data']:
        print("Invalid disconnect data received")
        return

    mac_address = data['data']['mac_address']
    if mac_address in clients:
        username = usernames.pop(mac_address, "Unknown")
        del clients[mac_address]
        gui_display.client_windows[mac_address].destroy()
        del gui_display.client_windows[mac_address]
        del gui_display.photo_labels[mac_address]
        gui_display.client_count -= 1
        gui_display.client_count_label.config(text=f"Clients connected: {gui_display.client_count}")
        gui_display.remove_connected_user(username)
        print(f"Client {username} disconnected.")
    response = {'status': 'disconnected'}
    conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))

def authenticate_client(conn):
    try:
        data = recv_all(conn)
        if not data:
            return False
        data = pickle.loads(data)


        print(f"Authentication request received: {data}")
        if data.get('action') == 'authenticate' and data.get('key') == SHARED_SECRET_KEY:
            response = {'status': 'authenticated'}
            conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))
            return True
        else:
            response = {'status': 'unauthenticated'}
            conn.sendall(len(pickle.dumps(response)).to_bytes(4, 'big') + pickle.dumps(response))
            return False
    except Exception as e:
        print(f"Authentication error: {e}")
        return False


def handle_client(conn, addr, gui_display):
    if not authenticate_client(conn):
        print(f"Client {addr} failed to authenticate.")
        conn.close()
        return

    print(f"Client {addr} authenticated successfully.")

    while server_running.is_set():
        try:
            data = recv_all(conn)
            if not data:
                break

            data = pickle.loads(data)
            action = data['action']
            if action == 'register':
                handle_register(data, conn, addr, gui_display)
            elif action == 'login':
                handle_login(data, conn, addr, gui_display)
            elif action == 'screenshot':
                handle_screenshot(data, conn, gui_display)
            elif action == 'disconnect':
                handle_disconnect(data, conn, gui_display)
                break
        except Exception as e:
            print(f"Error: {e}")
            break
    conn.close()

def start_server(gui_display):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # port = int
    # port = input("Enter port number: ")
    server.bind(('0.0.0.0', 9999))
    server.listen(5)
    server.settimeout(1)

    print("Server listening on port 9999...")

    while server_running.is_set():
        try:
            conn, addr = server.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr, gui_display))
            client_thread.start()
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error accepting connection: {e}")
            continue
    server.close()

if __name__ == "__main__":
    gui_display = ImageDisplay()
    server_thread = threading.Thread(target=start_server, args=(gui_display,))
    server_thread.start()

    tray_thread = threading.Thread(target=show_tray_icon, args=(gui_display,))
    tray_thread.daemon = True
    tray_thread.start()

    gui_display.run()
    server_running.clear()
    server_thread.join()
