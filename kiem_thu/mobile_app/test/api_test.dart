import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:parkly_mobile/api.dart';
import 'package:parkly_mobile/common.dart';

class MemoryStore implements SessionStore {
  final Map<String, String> values = {};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }
}

http.Response jsonResponse(dynamic data, [int status = 200]) => http.Response(
  jsonEncode(data),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

void main() {
  test(
    'Server configuration rejects credentials, fragments and dashboard URLs',
    () {
      expect(
        normalizeServer(' http://192.168.1.9:8002/ '),
        'http://192.168.1.9:8002',
      );
      for (final value in [
        'file:///tmp',
        'http://user:pass@host',
        'http://host/dashboard/',
        'http://host?token=secret',
        'http://host/#overview',
      ]) {
        expect(() => normalizeServer(value), throwsA(isA<ApiError>()));
      }
    },
  );
  test(
    'Authenticated requests send JSON and preserve Vietnamese error details',
    () async {
      final api = ParkingApi(
        server: 'http://test',
        client: MockClient((req) async {
          expect(req.headers['Authorization'], 'Bearer test-token');
          expect(jsonDecode(req.body)['full_name'], 'Nguyễn Văn An');
          return jsonResponse({'detail': 'Biển số đã được đăng ký'}, 409);
        }),
      )..token = 'test-token';
      await expectLater(
        api.object(
          '/auth/me',
          method: 'PATCH',
          body: {'full_name': 'Nguyễn Văn An'},
        ),
        throwsA(
          isA<ApiError>().having(
            (e) => e.message,
            'message',
            'Biển số đã được đăng ký',
          ),
        ),
      );
    },
  );
  test(
    'Login stores only token and server change removes authorization',
    () async {
      final store = MemoryStore();
      final auth = AuthState(
        store: store,
        api: ParkingApi(
          server: 'http://old',
          client: MockClient((r) async {
            expect(r.headers.containsKey('Authorization'), false);
            return jsonResponse({
              'access_token': 'opaque-token',
              'user': {'id': 9, 'full_name': 'Khách', 'role': 'CUSTOMER'},
            });
          }),
        ),
      );
      await auth.login('customer@example.com', 'test-password');
      expect(store.values['parkly-token'], 'opaque-token');
      expect(store.values.values, isNot(contains('test-password')));
      await auth.changeServer('http://new:8002');
      expect(auth.user, isNull);
      expect(auth.api.token, isNull);
      expect(store.values.containsKey('parkly-token'), false);
      expect(auth.api.server, 'http://new:8002');
    },
  );
  test('Expired session clears token while an ordinary rejected login does not emit expiry', () async {
    final api = ParkingApi(
      server: 'http://test',
      client: MockClient(
        (_) async => jsonResponse({'detail': 'Token hết hạn'}, 401),
      ),
    );
    var expiry = 0;
    api.onExpired = () => expiry++;
    await expectLater(
      api.object('/auth/login', authenticated: false),
      throwsA(isA<ApiError>()),
    );
    expect(expiry, 0);
    api.token = 'old-token';
    await expectLater(api.object('/auth/me'), throwsA(isA<ApiError>()));
    expect(expiry, 1);
    expect(api.token, isNull);
  });

  test('Automatic connection never sends a token to a different server', () async {
    final store = MemoryStore();
    store.values['parkly-token'] = 'previous-token';
    store.values['parkly-token-server'] = 'http://previous:8001';
    final requests = <http.Request>[];
    final auth = AuthState(
      store: store,
      discoverServer: () async => 'http://discovered:8001',
      api: ParkingApi(
        server: 'http://127.0.0.1:8001',
        client: MockClient((request) async {
          requests.add(request);
          return jsonResponse({
            'access_token': 'new-token',
            'user': {'id': 1, 'role': 'CUSTOMER'},
          });
        }),
      ),
    );

    await auth.boot();
    expect(auth.api.server, 'http://discovered:8001');
    expect(auth.api.token, isNull);
    expect(requests, isEmpty);
    await auth.login('customer@example.com', 'test-password');
    expect(requests.single.url.host, 'discovered');
    expect(requests.single.headers['Authorization'], isNull);
    expect(store.values['parkly-token-server'], 'http://discovered:8001');
    expect(store.values.containsKey('parkly-server'), isFalse);
  });
  test(
    'A temporary boot connection failure retains session for retry',
    () async {
      final store = MemoryStore()..values['parkly-token'] = 'existing';
      final auth = AuthState(
        store: store,
        api: ParkingApi(
          server: 'http://test',
          client: MockClient(
            (_) async => throw http.ClientException('offline'),
          ),
        ),
      );
      await auth.boot();
      expect(auth.bootError, isNotNull);
      expect(store.values['parkly-token'], 'existing');
      expect(auth.api.token, 'existing');
    },
  );
  test('Late response for an old parking lot cannot replace the newly selected lot', () async {
    final old = Completer<http.Response>();
    final api = ParkingApi(
      server: 'http://test',
      client: MockClient((r) async {
        if (r.url.path == '/parking-lots') {
          return jsonResponse([
            {'id': 1, 'name': 'A'},
            {'id': 2, 'name': 'B'},
          ]);
        }
        if (r.url.path.endsWith('/snapshot')) {
          return jsonResponse({'detail': 'Not Found'}, 404);
        }
        if (r.url.path == '/parking-spots') {
          if (r.url.queryParameters['parking_lot_id'] == '1') return old.future;
          return jsonResponse([
            {'id': 22, 'spot_code': 'B-001'},
          ]);
        }
        if (r.url.path.endsWith('/capacity')) {
          return jsonResponse({'groups': []});
        }
        return jsonResponse([]);
      }),
    );
    final auth = AuthState(api: api, store: MemoryStore())
      ..user = {'id': 1, 'role': 'CUSTOMER'};
    final data = ParkingData(auth);
    final first = data.load();
    await Future<void>.delayed(Duration.zero);
    data.lotId = 2;
    await data.load(force: true);
    expect(data.spots.single['id'], 22);
    old.complete(
      jsonResponse([
        {'id': 11},
      ]),
    );
    await first;
    expect(data.spots.single['id'], 22);
    data.dispose();
  });

  test('A refresh during a load triggers one follow-up with the newest spots', () async {
    final started = Completer<void>();
    final pending = Completer<http.Response>();
    final followUpStarted = Completer<void>();
    final followUp = Completer<http.Response>();
    var reads = 0;
    http.Response parking(String status) => jsonResponse({
      'spots': [{'id': 1, 'status': status}],
      'capacity': {'groups': []},
    });
    final auth = AuthState(
      store: MemoryStore(),
      api: ParkingApi(server: 'http://test', client: MockClient((request) async {
        final path = request.url.path;
        if (path == '/parking-lots') return jsonResponse([{'id': 1}]);
        if (path.endsWith('/snapshot')) {
          reads++;
          if (reads == 1) {
            started.complete();
            return pending.future;
          }
          followUpStarted.complete();
          return followUp.future;
        }
        return jsonResponse([]);
      })),
    )..user = {'id': 1, 'role': 'CUSTOMER'};
    final data = ParkingData(auth);
    final first = data.load();
    await started.future;
    final updates = Future.wait([data.load(), data.load()]);
    expect(reads, 1);
    pending.complete(parking('AVAILABLE'));
    await followUpStarted.future;
    await first.timeout(const Duration(seconds: 2));
    followUp.complete(parking('OCCUPIED'));
    await updates;
    expect(reads, 2);
    expect(data.spots.single['status'], 'OCCUPIED');
    data.dispose();
  });

  test(
    'Booking deadline is two hours in Vietnam wall time across midnight',
    () {
      final start = DateTime.utc(2026, 10, 27, 23, 30);
      expect(wallTime(bookingExpiry(start)), '2026-10-28T01:30:00');
      expect(dateText('2026-10-27T00:30:00Z'), '27/10/2026 07:30');
      expect(dateText('2026-10-27T00:30:00'), '27/10/2026 00:30');
    },
  );
  test('Spot compatibility checks both vehicle category and energy source', () {
    final electric = {'vehicle_type': 'MOTORBIKE', 'energy_type': 'ELECTRIC'};
    expect(
      compatible(electric, {
        'spot_type': 'MOTORBIKE',
        'energy_type': 'ELECTRIC',
      }),
      true,
    );
    expect(
      compatible(electric, {
        'spot_type': 'MOTORBIKE',
        'energy_type': 'GASOLINE',
      }),
      false,
    );
    expect(
      compatible(electric, {'spot_type': 'CAR', 'energy_type': 'ELECTRIC'}),
      false,
    );
  });
}
