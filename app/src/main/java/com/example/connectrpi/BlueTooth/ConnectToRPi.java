package com.example.connectrpi.BlueTooth;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.util.Log;
import android.widget.TextView;
import android.widget.Toast;

import com.example.connectrpi.MainActivity;

import java.io.IOException;
import java.util.UUID;

public class ConnectToRPi {
    private final MainActivity activity;
    private final BluetoothAdapter adapter;
    private final String address;
    private final UUID uuid;
    private final TextView tv;

    public ConnectToRPi(MainActivity activity, BluetoothAdapter adapter, String address, UUID uuid, TextView tv) {
        this.activity = activity;
        this.adapter = adapter;
        this.address = address;
        this.uuid = uuid;
        this.tv = tv;
    }

    @SuppressLint("MissingPermission")
    public void connectToRaspberryPi() {
        new Thread(() -> {
            try {
                if (activity.bluetoothSocket != null) activity.bluetoothSocket.close();

                BluetoothDevice device = adapter.getRemoteDevice(address);
                activity.bluetoothSocket = device.createRfcommSocketToServiceRecord(uuid);

                Log.d("BT_LOG", "연결 시도 중...");
                activity.bluetoothSocket.connect();
                Log.d("BT_LOG", "연결 성공!");

                // 메인 액티비티의 스트림 변수 초기화 (중요!)
                activity.outputStream = activity.bluetoothSocket.getOutputStream();
                activity.inputStream = activity.bluetoothSocket.getInputStream();

                // 수신 시작
                ReceiveData receiveData = new ReceiveData(activity, activity.inputStream, tv);
                receiveData.beginListenForData();

                activity.runOnUiThread(() -> Toast.makeText(activity, "라즈베리 파이 연결 성공!", Toast.LENGTH_SHORT).show());
            } catch (IOException e) {
                Log.e("BT_LOG", "연결 실패: " + e.getMessage());
                activity.runOnUiThread(() -> Toast.makeText(activity, "연결 실패: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }
}