package com.example.connectrpi;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.RequiresApi;
import androidx.appcompat.app.AppCompatActivity;
import com.example.connectrpi.R;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;

public class MainActivity extends AppCompatActivity {
    // 1. 라즈베리 파이 설정 정보
    private static final String DEVICE_ADDRESS = "2C:CF:67:8C:2B:B0";
    private static final UUID BT_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");

    // 2. 통신 관련 변수
    private BluetoothAdapter bluetoothAdapter;
    private BluetoothSocket bluetoothSocket;
    private OutputStream outputStream;
    private InputStream inputStream;
    private Thread workerThread;
    private boolean isRunning = false;
    boolean connected = false;

    // 3. UI 컴포넌트
    private EditText sentmessage;
    private TextView receiveText; // 받은 메시지를 보여줄 텍스트뷰 (있다고 가정)


    @RequiresApi(api = Build.VERSION_CODES.S)
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // 권한 요청
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{
                    Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT
            }, 100);
        }

        BluetoothManager bluetoothManager = getSystemService(BluetoothManager.class);
        this.bluetoothAdapter = bluetoothManager.getAdapter();

        // UI 연결
        sentmessage = findViewById(R.id.send_Text);
        receiveText = findViewById(R.id.receiveText); // XML에 id가 receive_Text인 TextView가 있다면 주석 해제

        // 버튼 클릭 리스너
        findViewById(R.id.connect_button).setOnClickListener(v -> connectToRaspberryPi());
        findViewById(R.id.Send_BTN).setOnClickListener(v -> sendMessage());
    }

    // [연결 메서드]
    @SuppressLint("MissingPermission")
    private void connectToRaspberryPi() {
        new Thread(() -> {
            try {
                if (bluetoothSocket != null) { bluetoothSocket.close(); }
                if (connected){
                    Toast.makeText(this, "이미 연결되어 있습니다.", Toast.LENGTH_SHORT).show();
                }

                BluetoothDevice device = bluetoothAdapter.getRemoteDevice(DEVICE_ADDRESS);
                bluetoothSocket = device.createRfcommSocketToServiceRecord(BT_UUID);

                Log.d("BT_LOG", "연결 시도 중...");
                bluetoothSocket.connect();
                Log.d("BT_LOG", "연결 성공!");
                // 연결 성공 시 즉시 수신 쓰레드 시작
                beginListenForData();
                // 스트림 초기화
                outputStream = bluetoothSocket.getOutputStream();
                inputStream = bluetoothSocket.getInputStream();
                //연결 여부
                connected = true;
                runOnUiThread(() -> Toast.makeText(this, "연결 성공!", Toast.LENGTH_SHORT).show());
            } catch (IOException e) {
                Log.e("BT_LOG", "연결 실패: " + e.getMessage());
                runOnUiThread(() -> Toast.makeText(this, "연결 실패: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    // [메시지 전송 메서드 - 실시간]
    private void sendMessage() {
        if (bluetoothSocket == null || !bluetoothSocket.isConnected()) {
            Toast.makeText(this, "먼저 연결하세요!", Toast.LENGTH_SHORT).show();
            return;
        }

        new Thread(() -> {
            try {
                String msg = sentmessage.getText().toString();
                String msgWithNewline = msg + "\n";
                outputStream.write(msgWithNewline.getBytes("UTF-8"));
                outputStream.flush();
                Log.d("BT_LOG", "전송 완료: " + msgWithNewline);
            } catch (IOException e) {
                Log.e("BT_LOG", "전송 실패: " + e.getMessage());
            }
        }).start();
    }

    // [실시간 메시지 수신 메서드]
    private void beginListenForData() {
        isRunning = true;
        workerThread = new Thread(() -> {
            byte[] buffer = new byte[1024];
            while (isRunning && !Thread.currentThread().isInterrupted()) {
                try {
                    // 데이터가 올 때까지 Blocking 대기 (가장 빠름)
                    int bytesRead = inputStream.read(buffer);
                    if (bytesRead > 0) {
                        String data = new String(buffer, 0, bytesRead, "UTF-8");

                        runOnUiThread(() -> {
                            Log.d("BT_LOG", "받은 메시지: " + data);
                            receiveText.append(data + "\n");
                        });
                    }
                } catch (IOException e) {
                    Log.e("BT_LOG", "수신 끊김: " + e.getMessage());
                    isRunning = false;
                    break;
                }
            }
        });
        workerThread.start();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        try {
            isRunning = false;
            if (workerThread != null) workerThread.interrupt();
            if (bluetoothSocket != null) bluetoothSocket.close();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}