import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:parkly_mobile/api.dart';
import 'package:parkly_mobile/common.dart';
import 'package:parkly_mobile/main.dart';
import 'package:parkly_mobile/screens.dart';

import 'api_test.dart' show MemoryStore, jsonResponse;

void main() {
  for (final scheduled in [false, true]) {
    testWidgets(
      scheduled
          ? 'Scheduled booking looks up and submits a full time window'
          : 'Booking previews the cutoff and lets the server set it',
      (tester) async {
        Json? sent;
        Map<String, String>? searched;
        final spot = {
          'id': 4,
          'spot_code': 'MG-001',
          'spot_type': 'MOTORBIKE',
          'energy_type': 'GASOLINE',
          'available_for_booking': true,
        };
        final api = ParkingApi(
          server: 'http://test',
          client: MockClient((request) async {
            if (request.url.path == '/reservations/policy') {
              return jsonResponse({
                'max_advance_minutes': 120,
                'checkin_window_minutes': 120,
                'server_time': wallTime(vietnamNow()),
              });
            }
            if (request.url.path == '/reservations' &&
                request.method == 'POST') {
              sent = jsonDecode(request.body) as Json;
              return jsonResponse({'id': 8}, 201);
            }
            if (request.url.path == '/reservations/available-spots') {
              searched = request.url.queryParameters;
              return jsonResponse([spot]);
            }
            return jsonResponse([]);
          }),
        )..token = 'customer';
        final auth = AuthState(api: api, store: MemoryStore())
          ..user = {'id': 1, 'role': 'CUSTOMER'};
        final vehicle = {
          'id': 2,
          'license_plate': '59A1-12345',
          'vehicle_type': 'MOTORBIKE',
          'energy_type': 'GASOLINE',
        };
        final data = ParkingData(auth)
          ..lotId = 1
          ..vehicles = [vehicle]
          ..spots = [spot];
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) {
                return Scaffold(
                  body: TextButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => BookingScreen(
                          data: data,
                          initialSpot: spot,
                          initialVehicleId: 2,
                        ),
                      ),
                    ),
                    child: const Text('Mở đặt chỗ'),
                  ),
                );
              },
            ),
          ),
        );
        await tester.tap(find.text('Mở đặt chỗ'));
        await tester.pumpAndSettle();
        if (scheduled) {
          final toggle = find.text('Đặt theo khung giờ');
          await tester.scrollUntilVisible(toggle, 150);
          await tester.tap(toggle);
          await tester.pumpAndSettle();
          expect(searched?['parking_lot_id'], '1');
          expect(searched?['vehicle_type'], 'MOTORBIKE');
          expect(searched?['end_time'], isNotNull);
        }
        await tester.scrollUntilVisible(
          find.text('Tự hủy nếu chưa nhận xe'),
          150,
        );
        if (!scheduled) {
          expect(
            find.textContaining('Chọn giờ đến trong 2 giờ tới'),
            findsOneWidget,
          );
        }
        await tester.scrollUntilVisible(find.text('Xác nhận đặt chỗ'), 150);
        await tester.tap(find.text('Xác nhận đặt chỗ'));
        await tester.pumpAndSettle();
        expect(sent?.keys.toSet(), {
          'vehicle_id',
          'parking_spot_id',
          'start_time',
          if (scheduled) 'end_time',
        });
        if (scheduled) {
          expect(sent?['end_time'], searched?['end_time']);
          expect(sent?['start_time'], searched?['start_time']);
        }
        expect(sent?['vehicle_id'], 2);
        expect(sent?['parking_spot_id'], 4);
        expect(find.text('Mở đặt chỗ'), findsOneWidget);
        await tester.pumpWidget(const SizedBox.shrink());
        data.dispose();
        auth.dispose();
        api.client.close();
      },
    );
  }

  testWidgets('Token expiry closes a private route and returns to login', (
    tester,
  ) async {
    final api = ParkingApi(
      server: 'http://test',
      client: MockClient(
        (r) async => r.url.path == '/auth/me'
            ? jsonResponse({'detail': 'Token hết hạn'}, 401)
            : jsonResponse([]),
      ),
    )..token = 'expired';
    final auth = AuthState(api: api, store: MemoryStore())
      ..booting = false
      ..user = {
        'id': 1,
        'full_name': 'Khách hàng',
        'email': 'customer@example.com',
        'role': 'CUSTOMER',
      };
    await tester.pumpWidget(ParklyApp(auth: auth));
    await tester.pumpAndSettle();
    final context = tester.element(find.byType(HomeShell));
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => const Scaffold(body: Text('Dữ liệu riêng của khách')),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Dữ liệu riêng của khách'), findsOneWidget);
    await expectLater(api.object('/auth/me'), throwsA(isA<ApiError>()));
    await tester.pumpAndSettle();
    expect(find.text('Đăng nhập'), findsOneWidget);
    expect(find.text('Dữ liệu riêng của khách'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    api.client.close();
    auth.dispose();
  });
  testWidgets('Login and registration remain usable at 360px with large text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final auth = AuthState(
      api: ParkingApi(server: 'http://10.0.2.2:8001'),
      store: MemoryStore(),
    )..booting = false;
    await tester.pumpWidget(ParklyApp(auth: auth));
    await tester.pumpAndSettle();
    expect(find.text('Đăng nhập'), findsOneWidget);
    await tester.ensureVisible(find.text('Chưa có tài khoản? Đăng ký'));
    await tester.tap(find.text('Chưa có tài khoản? Đăng ký'));
    await tester.pumpAndSettle();
    expect(find.text('Họ và tên'), findsOneWidget);
    expect(find.text('Ngày tháng năm sinh'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Nguồn năng lượng'),
      250,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Biển số xe'), findsOneWidget);
    expect(find.text('Loại xe'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    auth.api.client.close();
    auth.dispose();
  });
}
