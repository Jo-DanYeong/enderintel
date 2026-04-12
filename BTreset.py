import subprocess
import time

def reset_bluetooth_communication():
    """
    Resets the Bluetooth hardware and restarts the stack to clear any hung connections.
    """
    print("--- Resetting Bluetooth Communication ---")
    
    def run_cmd(args):
        try:
            subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"Error executing {' '.join(args)}: {e}")

    try:
        # 1. Kill any existing bluetoothctl processes
        print("Cleaning up background processes...")
        run_cmd(["sudo", "pkill", "bluetoothctl"])
        
        # 2. Power Down
        print("Powering off Bluetooth...")
        run_cmd(["bluetoothctl", "power", "off"])
        time.sleep(1)
        
        # 3. Restart the system bluetooth service
        print("Restarting Bluetooth system service...")
        run_cmd(["sudo", "systemctl", "restart", "bluetooth"])
        time.sleep(2) # Give it time to initialize
        
        # 4. Power Up and Re-enable Visibility
        print("Powering on and restoring visibility...")
        run_cmd(["bluetoothctl", "power", "on"])
        run_cmd(["bluetoothctl", "discoverable", "on"])
        run_cmd(["bluetoothctl", "pairable", "on"])
        
        print("--- Bluetooth Reset Complete ---")
        return True
    except Exception as e:
        print(f"Failed to reset Bluetooth: {e}")
        return False