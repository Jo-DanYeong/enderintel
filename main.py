from CommunicationSystem import CommunicationSys
import BTreset
import socket, os, time

server_socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
commuSys = CommunicationSys(server_socket)

if __name__ == "__main__":
    BTreset.reset_bluetooth_communication()#btl socket reset
    commuSys.CommSys()