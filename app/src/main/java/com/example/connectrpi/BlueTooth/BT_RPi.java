package com.example.connectrpi.BlueTooth;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.util.Log;
import android.widget.TextView;
import android.widget.Toast;
import com.example.connectrpi.BlueTooth.Util.Status;
import com.example.connectrpi.MainActivity;

import java.io.IOException;
import java.io.OutputStream;
import java.util.UUID;

public class BT_RPi {
    private ReceiveData receiveData;
    private final MainActivity activity;
    private final BluetoothAdapter adapter;
    private final String address;
    private final UUID uuid;
    private final TextView Receivedata;

    public BT_RPi(MainActivity activity, BluetoothAdapter adapter, String address, UUID uuid, TextView Receivedata) {
        this.activity = activity;
        this.adapter = adapter;
        this.address = address;
        this.uuid = uuid;
        this.Receivedata = Receivedata;
    }

    @SuppressLint("MissingPermission")
    public void connectToRaspberryPi() {
        new Thread(() -> {
            try {
                if (activity.bluetoothSocket != null) activity.bluetoothSocket.close();

                BluetoothDevice device = adapter.getRemoteDevice(address);
                activity.bluetoothSocket = device.createRfcommSocketToServiceRecord(uuid);
                receiveData = new ReceiveData(activity,activity.inputStream, Receivedata);

                Log.d("BT_LOG", "연결 시도 중...");
                activity.bluetoothSocket.connect();
                Log.d("BT_LOG", "연결 성공!");
                activity.runOnUiThread(() -> Toast.makeText(activity, "블루투스 연결 성공!", Toast.LENGTH_SHORT).show());

                //스트림 변수 초기화
                activity.outputStream = activity.bluetoothSocket.getOutputStream();
                activity.inputStream = activity.bluetoothSocket.getInputStream();

                // 수신 시작
                ReceiveData receiveData = new ReceiveData(activity, activity.inputStream, Receivedata);
                receiveData.beginListenForData();
            } catch (IOException e) {
                Log.e("BT_LOG", "연결 실패: " + e.getMessage());
                activity.runOnUiThread(() -> Toast.makeText(activity, "연결 실패 : 연결 대상의 전원 및 서버가 꺼져있습니다.", Toast.LENGTH_SHORT).show());
                Status.setIsRunning(false);
            }
        }).start();
    }

    public void disconnectToRaspberryPi(OutputStream os){
        new Thread(() -> {
            try{
                //만약 연결이 안돼있는 상태일때 실행 안하기
                if (!Status.getIsRunning()){
                    activity.runOnUiThread(() -> Toast.makeText(activity, "연결이 되어있지 않습니다.", Toast.LENGTH_SHORT).show());
                    return;
                }

                //서버로 신호 보내기
                SendMessage.MessageSend(os,"YzJoMWRHUnZkMjQ9");
                Log.d("BT_LOG", "연결 끊기 신호 보냄");
                activity.runOnUiThread(() -> Toast.makeText(activity, "연결이 정상적으로 끊어졌습니다.", Toast.LENGTH_SHORT).show());
                Status.setIsRunning(false);

            }catch (IOException e){
                Log.e("BT_LOG","에러 발생"+e.getMessage());
                activity.runOnUiThread(() -> Toast.makeText(activity, "에러 발생"+e.getMessage(), Toast.LENGTH_SHORT).show());
                Status.setIsRunning(false);
            }
        }).start();
    }
}