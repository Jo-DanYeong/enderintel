import socket, os
import BTreset

# 1. Initialize Bluetooth socket
# AF_BLUETOOTH: Bluetooth address family
# SOCK_STREAM: Sequential, reliable, two-way connection
# BTPROTO_RFCOMM: Communication protocol (Standard for Android)


server_socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
BTreset.reset_bluetooth_communication()#btl socket reset

try:
    # 2. Bind to any available address and port 1
    server_socket.bind(("2C:CF:67:8C:2B:B0", 1))
    server_socket.listen(1)
    
    print("--- Bluetooth Server Started ---")
    print("Waiting for connection on RFCOMM channel 1...")
    
    # 3. Wait for connection from Android
    client_socket, address = server_socket.accept()
    print(f"Connected! Device Address: {address}")

    while True:
        # 4. Receive data (max 1024 bytes)
        data = client_socket.recv(1024)
        if not data:
            break
 
        # 5. Decode received data to string
        message = data.decode('utf-8').strip()  
        response = "Undefined Value"
        print(f"Received: {message}")

        if message == "ping":
            response = "pong"

        elif message == "":
            response = "no value"

        else:
            response = "undefine Message"
        client_socket.send(response.encode('utf-8'))
        

except Exception as e:
    print(f"Error occurred: {e}")

except KeyboardInterrupt:
    print("\nquit")

finally:
    # 7. Close sockets
    if 'client_socket' in locals():
        client_socket.close()
    server_socket.close()
    print("Server stopped.")
