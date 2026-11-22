package vn.parkly.parkly_mobile

import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "vn.parkly/backend")
            .setMethodCallHandler { call, result ->
                if (call.method != "developmentHosts") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val hosts = getString(R.string.parkly_dev_hosts).split(',').filter { it.isNotBlank() }
                val emulator = Build.HARDWARE in listOf("goldfish", "ranchu") ||
                    Build.MODEL.startsWith("sdk_gphone")
                result.success(if (emulator) listOf("10.0.2.2") + hosts else hosts)
            }
    }
}
