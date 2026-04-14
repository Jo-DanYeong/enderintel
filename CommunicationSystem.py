import socket,time

class CommunicationSys:
    def __init__(self,server_soket):
        self.server_soket = server_soket      

    def CommSys(self):
        server_socket = self.server_soket

        try:
            # 2. Bind to any available address and port 1
            server_socket.bind(("2C:CF:67:8C:2B:B0", 1))
            server_socket.listen(1)
            
            print("--- Bluetooth Server Started ---")
                
            while True:
                print("\nWaiting for connection on RFCOMM channel 1...")
                client_socket = None

                try:   
                    # 3. Wait for connection from Android
                    client_socket, address = server_socket.accept()
                    print(f"Connected! Device Address: {address}")

                    while True:
                        try:
                            # 4. Receive data (max 1024 bytes)
                            data = client_socket.recv(1024)
                            if not data:
                                print("Client disconnected.")
                                break
                    
                            # 5. Decode received data to string
                            message = data.decode('utf-8').strip()  
                            response = "Undefined Value"
                            print(f"Received: {message}")
                            
                            if message == "YzJoMWRHUnZkMjQ9":
                                response = "shutdown complete"
                                break

                            elif message == "":
                                response = "no value"

                            elif message == "soul":
                                response = "delete messgae"

                            print(f"Sent : {response}\n")
                            client_socket.send(response.encode('utf-8'))

                        except ConnectionResetError:
                            print("Connection was reset by the client.")
                            break

                        except Exception as e:
                            print(f"Communication error: {e}")
                            break
                        
                    client_socket.close()

                    if 'message' in locals() and message == "YzJoMWRHUnZkMjQ9":
                        print("Stopping server by command...")
                        break

                except Exception as e:
                    print(f"Accept error: {e}")
                    time.sleep(1)

                finally:
                    if client_socket is not None:
                        try:
                            client_socket.close()
                            print("Client socket closed safely.")
                        except:
                            pass

        except KeyboardInterrupt:
            print("\nServer stopped by user.")

        finally:
            # 7. Close sockets
            if 'client_socket' in locals():
                client_socket.close()
            server_socket.close()
            print("Server stopped.")