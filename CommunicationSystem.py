import socket
import time
import threading
import os
 
 
class CommunicationSys:
    def __init__(self, server_socket, ai_trigger_callback=None):
        """
        server_socket       : �������� RFCOMM ����
        ai_trigger_callback : "ender" ���� ���� �� ȣ���� �Լ� (������ AI ��� ��Ȱ��)
        """
        self.server_socket = server_socket
        self._ai_trigger = ai_trigger_callback
 
    # ��������������������������������������������������������������������������������������������
    # ���� ����
    # ��������������������������������������������������������������������������������������������
    def _trigger_ai(self, client_socket):
        """AI ������������ ���� �����忡�� �����ϰ�, ����� BT�� ����."""
        if self._ai_trigger is None:
            client_socket.send("AI ����� ��Ȱ��ȭ �����Դϴ�.".encode("utf-8"))
            return
 
        def _run():
            try:
                # ai_trigger_callback �� (reply_text) -> None ����
                # pi_local/main.py �� EnderAssistant.on_triggered �� �����ؼ� �ѱ�
                reply = self._ai_trigger()          # ����ŷ (���� �� STT �� GPT �� TTS)
                if reply and client_socket:
                    try:
                        client_socket.send(reply.encode("utf-8"))
                    except Exception:
                        pass
            except Exception as e:
                print(f"[BT-AI] ���������� ����: {e}")
 
        threading.Thread(target=_run, daemon=True).start()

    def CommSys(self):
        server_socket = self.server_socket

        # Determine bind address from environment or fallback to previous MAC
        bind_addr = os.getenv("BT_BIND_ADDRESS", "E4:5F:01:7B:E6:3D")

        try:
            server_socket.bind((bind_addr, 1))
            server_socket.listen(1)
            print(f"--- Bluetooth Server Started (bound to {bind_addr}) ---")
 
            while True:
                print("\nWaiting for connection on RFCOMM channel 1...")
                client_socket = None
 
                try:
                    client_socket, address = server_socket.accept()
                    print(f"Connected! Device Address: {address}")
                    # register connected client socket in the RFCOMM bridge
                    try:
                        from backend import rfcomm_bridge
                        rfcomm_bridge.set_client_socket(client_socket)
                        print("[BT] Registered client socket in rfcomm_bridge")
                    except Exception:
                        pass
                    client_socket.send("Connected to Bluetooth Server".encode("utf-8"))
 
                    while True:
                        try:
                            data = client_socket.recv(1024)
                            if not data:
                                print("Client disconnected.")
                                break
 
                            message = data.decode("utf-8").strip()
                            print(f"Received: {message}")
 
                            match message:
 
                                # ���� AI �� Ʈ���� ����������������������������������������������������
                                case "ender" | "����" | "ai":
                                    print("[BT] AI ���������� Ʈ����")
                                    client_socket.send(
                                        "AI �񼭸� �����մϴ�. ������ �ּ���.".encode("utf-8")
                                    )
                                    self._trigger_ai(client_socket)
                                    # ������������ �񵿱�� ����, ������ ��� ���
                                    continue

                                # ���� ���� ���ɾ� ����������������������������������������������������������
                                case "YzJoMWRHUnZkMjQ5":        # shutdown
                                    client_socket.send("shutdown complete".encode("utf-8"))
                                    break
 
                                case "9d634e1a156dc0c1611eb4c3cff57276":  # disconnect
                                    client_socket.send("disconnected".encode("utf-8"))
                                    break
 
                                case "cmVjb25uZWN0":             # reconnect
                                    client_socket.send("Socket Reset...".encode("utf-8"))
                                    break
 
                                case "led":
                                    client_socket.send("LED toggled".encode("utf-8"))
 
                                case "":
                                    client_socket.send("no Value".encode("utf-8"))
 
                                case _:
                                    client_socket.send("undefined Value".encode("utf-8"))
 
                            print(f"Sent response for: {message}\n")
 
                        except ConnectionResetError:
                            print("Connection was reset by the client.")
                            break
                        except KeyboardInterrupt:
                            break
                        except Exception as e:
                            print(f"Communication error: {e}")
                            break
 
                    # shutdown �����̸� ������ ����
                    if "message" in dir() and message == "YzJoMWRHUnZkMjQ5":
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
                            try:
                                from backend import rfcomm_bridge
                                rfcomm_bridge.clear_client_socket()
                                print("[BT] Cleared client socket from rfcomm_bridge")
                            except Exception:
                                pass
                        except Exception:
                            pass
 
        except KeyboardInterrupt:
            print("\nServer stopped by user.")
        finally:
            server_socket.close()
            print("Server stopped.")
 