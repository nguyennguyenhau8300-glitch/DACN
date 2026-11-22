import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker_platform_interface/image_picker_platform_interface.dart';
import 'package:integration_test/integration_test.dart';
import 'package:parkly_mobile/api.dart';
import 'package:parkly_mobile/common.dart';
import 'package:parkly_mobile/main.dart';
import 'package:parkly_mobile/screens.dart';
import 'package:parkly_mobile/research_screens.dart';

import '../test/api_test.dart' show MemoryStore;

class FixturePicker extends ImagePickerPlatform {
  final String path;
  FixturePicker(this.path);
  @override
  Future<XFile?> getImageFromSource({
    required ImageSource source,
    ImagePickerOptions options = const ImagePickerOptions(),
  }) async => XFile(path);
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  const server = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8001',
  );
  late AuthState auth;

  Future<void> waitFor(
    WidgetTester tester,
    Finder finder, {
    int seconds = 30,
  }) async {
    final deadline = DateTime.now().add(Duration(seconds: seconds));
    bool present() { try { return finder.evaluate().isNotEmpty; } on StateError { return false; } }
    while (!present()) {
      if (DateTime.now().isAfter(deadline)) fail('Không tìm thấy $finder');
      await tester.pump(const Duration(milliseconds: 250));
    }
    await tester.pump(const Duration(milliseconds: 300));
  }

  Future<void> tap(WidgetTester tester, Finder finder) async {
    await waitFor(tester, finder);
    await tester.ensureVisible(finder);
    await tester.pump(const Duration(milliseconds: 250));
    await tester.tap(finder);
    await tester.pump(const Duration(milliseconds: 400));
  }

  Future<void> screenshot(WidgetTester tester, String name) async {
    await tester.pump(const Duration(milliseconds: 500));
    final response = await http.post(
      Uri.parse('$server/test-screenshot/$name'),
    );
    expect(response.statusCode, 200);
  }

  Future<void> login(WidgetTester tester, String role) async {
    auth = AuthState(
      api: ParkingApi(server: server),
      store: MemoryStore(),
    )..booting = false;
    await tester.pumpWidget(ParklyApp(auth: auth));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.enterText(
      find.byType(TextFormField).at(0),
      '$role@example.com',
    );
    await tester.enterText(find.byType(TextFormField).at(1), 'TestParking123!');
    await tap(tester, find.text('Đăng nhập'));
    await waitFor(tester, find.text('Ô tô điện'));
  }

  Future<void> close(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 300));
    auth.api.client.close();
    auth.dispose();
  }

  testWidgets(
    'Android customer books, cancels and edits profile against real PostgreSQL',
    (tester) async {
      await login(tester, 'customer');
      await screenshot(tester, 'Android-Tong-quan');
      await tap(tester, find.text('Bãi xe').last);
      await tap(tester, find.widgetWithText(ChoiceChip, 'Xe máy xăng'));
      await tap(tester, find.text('MG-003'));
      await tap(tester, find.text('Đặt chỗ này'));
      await waitFor(tester, find.byType(BookingScreen));
      await tap(tester, find.byType(DropdownButtonFormField<int>).first);
      await tap(tester, find.text('59A1-22222 · Xe máy xăng').last);
      await screenshot(tester, 'Android-Dat-cho');
      await tap(tester, find.text('Xác nhận đặt chỗ'));
      await waitFor(tester, find.byType(ParkingTab));
      await tap(tester, find.text('Đặt chỗ').last);
      await waitFor(tester, find.text('Hủy đặt chỗ'));
      await tap(tester, find.text('Hủy đặt chỗ'));
      await tap(tester, find.text('Xác nhận'));
      await waitFor(tester, find.text('Đã hủy'));
      await tap(tester, find.text('Tài khoản').last);
      await tap(tester, find.text('Sửa thông tin cá nhân'));
      await waitFor(tester, find.byType(ProfileForm));
      await tester.enterText(
        find.byType(TextFormField).at(0),
        'Khách hàng Android',
      );
      await tester.enterText(find.byType(TextFormField).at(1), 'Đà Nẵng');
      await tap(tester, find.text('Lưu thông tin'));
      await waitFor(tester, find.text('Khách hàng Android'));
      expect(auth.user!['hometown'], 'Đà Nẵng');
      await screenshot(tester, 'Android-Tai-khoan');
      expect(tester.takeException(), isNull);
      await close(tester);
    },
  );

  testWidgets(
    'Android staff checks in with real OCR, checks out, collects cash and handles an incident',
    (tester) async {
      await login(tester, 'admin');
      final fixture = File(
        '${Directory.systemTemp.path}/parkly-test-plate.png',
      );
      final bytes = await http.readBytes(
        Uri.parse('$server/test-fixtures/double.png'),
      );
      await fixture.writeAsBytes(bytes);
      final originalPicker = ImagePickerPlatform.instance;
      ImagePickerPlatform.instance = FixturePicker(fixture.path);
      addTearDown(() async {
        ImagePickerPlatform.instance = originalPicker;
        if (await fixture.exists()) await fixture.delete();
      });
      await tap(tester, find.text('Nhận diện biển số AI'));
      await waitFor(tester, find.byType(AiScreen));
      await tap(tester, find.text('Chọn ảnh'));
      await tap(tester, find.text('Nhận diện biển số'));
      final deadline = DateTime.now().add(const Duration(seconds: 125));
      while (find.textContaining('Điểm OCR:').evaluate().isEmpty &&
          find.byType(ErrorNotice).evaluate().isEmpty) {
        if (DateTime.now().isAfter(deadline)) break;
        await tester.pump(const Duration(milliseconds: 250));
      }
      await screenshot(tester, 'Android-AI-Ket-qua');
      if (find.byType(ErrorNotice).evaluate().isNotEmpty) {
        fail(
          tester.widget<ErrorNotice>(find.byType(ErrorNotice).first).message,
        );
      }
      await waitFor(tester, find.text('59A112345'), seconds: 5);
      await tap(tester, find.byType(DropdownButtonFormField<int>).first);
      await tap(tester, find.text('MG-004 · Xe máy xăng').last);
      await screenshot(tester, 'Android-Nhan-dien-AI');
      await tap(tester, find.text('Xác nhận xe vào'));
      await waitFor(tester, find.byType(OverviewTab));
      await tap(tester, find.text('Lịch sử gửi xe & thanh toán'));
      await waitFor(tester, find.text('Xác nhận xe ra'));
      await tap(tester, find.text('Xác nhận xe ra'));
      await tap(tester, find.text('Xác nhận'));
      await waitFor(tester, find.text('Thu tiền mặt'));
      await tap(tester, find.text('Thu tiền mặt'));
      await tap(tester, find.text('Xác nhận'));
      await waitFor(tester, find.text('Đã ghi nhận thanh toán tiền mặt.'));
      await tap(tester, find.text('Thanh toán').first);
      await waitFor(tester, find.textContaining('Biên nhận #'));
      await screenshot(tester, 'Android-Thanh-toan');
      final spots = await auth.api.list('/parking-spots');
      final electric = spots.firstWhere((s) => s['spot_code'] == 'CE-001');
      final device = await auth.api.object(
        '/iot/devices',
        method: 'POST',
        body: {
          'device_code': 'MOBILE-HOT',
          'parking_spot_id': electric['id'],
          'kind': 'CHARGER',
        },
      );
      final telemetry = ParkingApi(server: server, client: http.Client());
      final response = await telemetry.client.post(
        Uri.parse('$server/iot/devices/MOBILE-HOT/telemetry'),
        headers: {
          'X-API-Key': device['api_key'],
          'Content-Type': 'application/json',
        },
        body: '{"sequence":1,"charger_status":"READY","temperature_c":75}',
      );
      expect(response.statusCode, 200);
      telemetry.client.close();
      final routeContext = tester.element(find.byType(HistoryScreen));
      Navigator.of(routeContext).pop();
      await tester.pump(const Duration(milliseconds: 400));
      await tap(tester, find.text('Cảnh báo & sự cố'));
      await waitFor(tester, find.text('Quá nhiệt'));
      await tap(tester, find.text('Xác nhận tiếp nhận'));
      await waitFor(tester, find.text('Đã tiếp nhận'));
      await screenshot(tester, 'Android-Canh-bao');
      expect(tester.takeException(), isNull);
      await close(tester);
    },
  );

  testWidgets(
    'Android platform secure storage persists and removes an opaque value',
    (tester) async {
      final store = SecureSessionStore();
      await store.write('parkly-integration-probe', 'opaque-test-value');
      expect(await store.read('parkly-integration-probe'), 'opaque-test-value');
      await store.delete('parkly-integration-probe');
      expect(await store.read('parkly-integration-probe'), isNull);
    },
  );

  testWidgets('Android finds a lot, recommends a route and opens an internal QR checkout', (tester) async {
    await login(tester, 'customer');
    await tap(tester, find.text('Tìm bãi xe'));
    await waitFor(tester, find.byType(FindLotScreen));
    await tester.enterText(find.byType(TextField), 'Trung tâm');
    await tap(tester, find.text('Bãi xe Trung tâm'));
    await tap(tester, find.text('Gợi ý ô & đường đi'));
    await waitFor(tester, find.byType(RoutingScreen));
    await tap(tester, find.byType(DropdownButtonFormField<int>));
    await tap(tester, find.text('59A1-22222 · Xe máy xăng').last);
    await tap(tester, find.text('Tìm ô phù hợp'));
    await waitFor(tester, find.text('Đặt ô này').first);
    await screenshot(tester, 'Android-Goi-y-duong-di');
    final context = tester.element(find.byType(RoutingScreen));
    Navigator.pop(context);
    await tester.pump(const Duration(milliseconds: 400));
    final adminApi = ParkingApi(server: server);
    final loginResponse = await adminApi.object('/auth/login', method:'POST', body:{'email':'admin@example.com','password':'TestParking123!'}, authenticated:false);
    adminApi.token = loginResponse['access_token'];
    final vehicles = await auth.api.list('/vehicles');
    final spots = await auth.api.list('/parking-spots');
    final spot = spots.firstWhere((s)=>s['spot_type']=='MOTORBIKE' && s['energy_type']=='GASOLINE' && s['available_for_booking']==true);
    final entered = await adminApi.object('/parking-sessions/check-in',method:'POST',body:{'vehicle_id':vehicles.first['id'],'parking_spot_id':spot['id']});
    await adminApi.object('/parking-sessions/${entered['id']}/check-out',method:'POST',body:{});
    await tap(tester, find.text('Thanh toán thử nghiệm'));
    await waitFor(tester, find.byType(CheckoutScreen));
    await tester.pump(const Duration(seconds: 1));
    await tap(tester, find.byType(DropdownButtonFormField<int>));
    await tap(tester, find.textContaining('#${entered['id']}').last);
    await tap(tester, find.text('Tạo thanh toán thử'));
    await waitFor(tester, find.text('Mở trang mô phỏng'));
    await screenshot(tester, 'Android-QR-thu-nghiem');
    expect(tester.takeException(),isNull);
    adminApi.client.close();
    await close(tester);
  });
}
