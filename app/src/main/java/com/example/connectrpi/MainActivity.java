package com.example.connectrpi;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.widget.EditText;
import android.widget.TextView;

import androidx.annotation.RequiresApi;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;

import com.example.connectrpi.BlueTooth.ConnectToRPi;
import com.example.connectrpi.BlueTooth.SendMessage;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;

public class MainActivity extends AppCompatActivity {
    // 라즈베리 파이 설정 (상수는 static final 유지)
    private static final String DEVICE_ADDRESS = "2C:CF:67:8C:2B:B0";
    private static final UUID BT_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");

    // 통신 관련 변수 (다른 클래스에서 activity.변수명으로 접근)
    public BluetoothAdapter bluetoothAdapter;
    public BluetoothSocket bluetoothSocket;
    public OutputStream outputStream;
    public InputStream inputStream;

    // UI 컴포넌트
    private EditText sendMessageField;
    private TextView receiveText;

    @RequiresApi(api = Build.VERSION_CODES.S)
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        //권한 요청
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[]{
                    Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT
            }, 100);
        }

        // 블루투스 어댑터 초기화
        BluetoothManager bluetoothManager = getSystemService(BluetoothManager.class);
        bluetoothAdapter = bluetoothManager.getAdapter();

        // UI 연결
        sendMessageField = findViewById(R.id.send_Text);
        receiveText = findViewById(R.id.receiveText);

        // 버튼 리스너
        findViewById(R.id.connect_button).setOnClickListener(v -> {
            ConnectToRPi connector = new ConnectToRPi(this, bluetoothAdapter, DEVICE_ADDRESS, BT_UUID, receiveText);
            connector.connectToRaspberryPi();
        });

        //블루투스 연결 해제
        findViewById(R.id.disconnect_button).setOnClickListener(v ->{
            BT_RPi connector = new BT_RPi(this, bluetoothAdapter, DEVICE_ADDRESS, BT_UUID, receiveText);
            Status.setIsRunning(false);
            connector.disconnectToRaspberryPi(outputStream);
        });

        //
        findViewById(R.id.Send_BTN).setOnClickListener(v -> {
            // 현재 소켓 상태를 확인하여 전달
            boolean isConnected = (bluetoothSocket != null && bluetoothSocket.isConnected());
            SendMessage sender = new SendMessage(this, outputStream, sendMessageField, isConnected);
            sender.sendMessage();
        });
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        try {
            if (bluetoothSocket != null) bluetoothSocket.close();
        } catch (IOException e) {
            Log.e("MainActivity", "소켓 닫기 실패", e);
        }
    }
}