import socket,time

class CommunicationSys:
    def __init__(self,server_soket):
        self.server_soket = server_soket      

    def CommSys(self):
        server_socket = self.server_soket

        try:
            # 2. Bind to any available address and port 1
            server_socket.bind(("E4:5F:01:7B:E6:3D", 1))
            server_socket.listen(1)
            
            print("--- Bluetooth Server Started ---")
                
            while True:
                print("\nWaiting for connection on RFCOMM channel 1...")
                client_socket = None
                response = "Undefine Message"

                try:   
                    # 3. Wait for connection from Android
                    client_socket, address = server_socket.accept()
                    print(f"Connected! Device Address: {address}")
                    response = "Connected to Bluetooth Server"
                        
                    client_socket.send(response.encode('utf-8'))

                    while True:
                        try:
                            # 4. Receive data (max 1024 bytes)
                            data = client_socket.recv(1024)
                            if not data:
                                print("Client disconnected.")
                                break
                    
                            # 5. Decode received data to string
                            message = data.decode('utf-8').strip()
                            print(f"Received: {message}")
                            match(message):
                                case "led":
                                    response = "LED toggled"
                                    client_socket.send(response.encode('utf-8'))
                                    
                                case "":
                                    response = "no Value"
				                
                                case _:
                                    response = "undefine Value"
                            response += "\n"
                            print(f"Sent : {response}\n")
                            client_socket.send(response.encode('utf-8'))

                        except ConnectionResetError:
                            print("Connection was reset by the client.")
                            break

                        except Exception as e:
                            print(f"Communication error: {e}")
                            break

                        except KeyboardInterrupt:
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
