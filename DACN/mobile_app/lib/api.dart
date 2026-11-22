import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

typedef Json = Map<String, dynamic>;

class ApiError implements Exception {
  final String message;
  final int? status;
  const ApiError(this.message, [this.status]);
  @override
  String toString() => message;
}

String normalizeServer(String input) {
  final uri = Uri.tryParse(input.trim());
  if (uri == null ||
      !['http', 'https'].contains(uri.scheme) ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      !['', '/'].contains(uri.path)) {
    throw const ApiError(
      'Nhập địa chỉ backend, ví dụ http://192.168.1.10:8001 (không thêm /dashboard).',
    );
  }
  return uri.replace(path: '').toString();
}

abstract class SessionStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class SecureSessionStore implements SessionStore {
  final FlutterSecureStorage storage;
  SecureSessionStore([this.storage = const FlutterSecureStorage()]);
  @override
  Future<String?> read(String key) => storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => storage.delete(key: key);
}

class ParkingApi {
  final http.Client client;
  String server;
  String? token;
  VoidCallback? onExpired;
  ParkingApi({required this.server, http.Client? client})
    : client = client ?? http.Client();

  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Json? body,
    bool authenticated = true,
  }) async {
    final headers = <String, String>{'Accept': 'application/json'};
    final requestToken = authenticated ? token : null;
    final requestServer = server;
    if (requestToken != null) headers['Authorization'] = 'Bearer $requestToken';
    if (body != null) headers['Content-Type'] = 'application/json';
    try {
      final req = http.Request(method, Uri.parse('$server$path'))
        ..headers.addAll(headers);
      if (body != null) req.body = jsonEncode(body);
      final response = await http.Response.fromStream(
        await client.send(req).timeout(const Duration(seconds: 20)),
      ).timeout(const Duration(seconds: 20));
      return decode(response, requestToken, requestServer);
    } on TimeoutException {
      throw const ApiError('Máy chủ phản hồi chậm. Hãy thử lại.');
    } on http.ClientException {
      throw const ApiError(
        'Không kết nối được backend. Kiểm tra địa chỉ máy chủ và Wi-Fi.',
      );
    }
  }

  dynamic decode(
    http.Response response,
    String? requestToken,
    String requestServer,
  ) {
    dynamic data;
    try {
      data = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      data = null;
    }
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (data == null) {
        throw const ApiError('Máy chủ trả dữ liệu không hợp lệ.');
      }
      return data;
    }
    if (response.statusCode == 401 &&
        requestServer == server &&
        requestToken != null &&
        requestToken == token) {
      token = null;
      onExpired?.call();
    }
    final detail = data is Map ? data['detail'] : null;
    final message = detail is String
        ? detail
        : detail is List
        ? detail
              .map((e) => e is Map ? e['msg'].toString() : e.toString())
              .join('\n')
        : 'Yêu cầu thất bại (${response.statusCode}).';
    throw ApiError(message, response.statusCode);
  }

  Future<Json> object(
    String path, {
    String method = 'GET',
    Json? body,
    bool authenticated = true,
  }) async {
    final value = await request(
      path,
      method: method,
      body: body,
      authenticated: authenticated,
    );
    if (value is! Map) {
      throw const ApiError('Dữ liệu máy chủ không đúng định dạng.');
    }
    return Map<String, dynamic>.from(value);
  }

  Future<List<Json>> list(String path) async {
    final value = await request(path);
    if (value is! List) {
      throw const ApiError('Danh sách từ máy chủ không hợp lệ.');
    }
    return value.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Json> parkingSnapshot(int lotId) async {
    try {
      return await object('/parking-lots/$lotId/snapshot');
    } on ApiError catch (error) {
      if (error.status != 404) rethrow;
      // An app installed separately can also connect to an older Parkly server.
      final parts = await Future.wait<dynamic>([
        list('/parking-spots?parking_lot_id=$lotId'),
        object('/parking-lots/$lotId/capacity'),
      ]);
      return {'spots': parts[0], 'capacity': parts[1]};
    }
  }

  Future<Json> photo(
    String path,
    Uint8List bytes,
    String filename, {
    Map<String, String> fields = const {},
  }) async {
    if (bytes.length > 8 * 1024 * 1024) {
      throw const ApiError('Ảnh tối đa 8 MB.');
    }
    final extension = filename.split('.').last.toLowerCase();
    final types = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'webp': 'webp'};
    if (!types.containsKey(extension)) {
      throw const ApiError('Chọn ảnh JPEG, PNG hoặc WebP.');
    }
    final requestToken = token;
    final requestServer = server;
    final req = http.MultipartRequest('POST', Uri.parse('$server$path'))
      ..fields.addAll(fields);
    if (requestToken != null) {
      req.headers['Authorization'] = 'Bearer $requestToken';
    }
    req.files.add(
      http.MultipartFile.fromBytes(
        'file',
        bytes,
        filename: filename,
        contentType: MediaType('image', types[extension]!),
      ),
    );
    try {
      final response = await http.Response.fromStream(
        await client.send(req).timeout(const Duration(seconds: 120)),
      ).timeout(const Duration(seconds: 120));
      return Map<String, dynamic>.from(
        decode(response, requestToken, requestServer) as Map,
      );
    } on TimeoutException {
      throw const ApiError('Nhận diện quá lâu. Hãy thử ảnh khác.');
    } on http.ClientException {
      throw const ApiError('Không gửi được ảnh đến máy chủ.');
    }
  }
}

class AuthState extends ChangeNotifier {
  final ParkingApi api;
  final SessionStore store;
  final Future<String?> Function()? discoverServer;
  final String _defaultServer;
  bool _hasServerOverride = false;
  Json? user;
  bool booting = true;
  String? bootError;
  int revision = 0;
  AuthState({required this.api, required this.store, this.discoverServer})
    : _defaultServer = api.server {
    api.onExpired = () {
      unawaited(logout());
    };
  }
  bool get staff =>
      const ['ADMIN', 'MANAGER', 'SECURITY'].contains(user?['role']);
  bool get admin => user?['role'] == 'ADMIN';

  Future<void> boot() async {
    booting = true;
    bootError = null;
    notifyListeners();
    try {
      final savedServer = await store.read('parkly-server');
      _hasServerOverride = savedServer != null;
      final token = await store.read('parkly-token');
      final tokenServer = await store.read('parkly-token-server');
      if (savedServer != null) {
        api.server = normalizeServer(savedServer);
      } else if (discoverServer != null) {
        api.server = await discoverServer!() ?? tokenServer ?? _defaultServer;
      } else {
        api.server = _defaultServer;
      }
      final boundElsewhere = tokenServer != null && tokenServer != api.server;
      final unboundAutomaticToken =
          tokenServer == null && !_hasServerOverride && discoverServer != null;
      if (token != null && (boundElsewhere || unboundAutomaticToken)) {
        await logout();
      } else {
        api.token = token;
      }
      user = api.token == null ? null : await api.object('/auth/me');
    } on ApiError catch (e) {
      if (e.status != 401) bootError = e.message;
    } catch (_) {
      bootError =
          'Không đọc được phiên đăng nhập. Bạn có thể đăng xuất và thử lại.';
    } finally {
      booting = false;
      notifyListeners();
    }
  }

  Future<void> login(String email, String password) async {
    if (!_hasServerOverride) {
      final discovered = await discoverServer?.call();
      if (discovered != null) api.server = discovered;
    }
    final server = api.server;
    final data = await api.object(
      '/auth/login',
      method: 'POST',
      authenticated: false,
      body: {'email': email.trim(), 'password': password},
    );
    if (api.server != server) {
      throw const ApiError('Máy chủ đã thay đổi. Hãy đăng nhập lại.');
    }
    final token = data['access_token'] as String;
    // Save first: a storage failure must not leave the UI claiming a persisted login.
    await store.write('parkly-token-server', server);
    await store.write('parkly-token', token);
    if (api.server != server) {
      throw const ApiError('Máy chủ đã thay đổi. Hãy đăng nhập lại.');
    }
    api.token = token;
    user = Map<String, dynamic>.from(data['user'] as Map);
    bootError = null;
    revision++;
    notifyListeners();
  }

  Future<void> logout() async {
    api.token = null;
    user = null;
    bootError = null;
    revision++;
    notifyListeners();
    await store.delete('parkly-token');
    await store.delete('parkly-token-server');
  }

  Future<void> changeServer(String value) async {
    final server = normalizeServer(value);
    await logout();
    await store.write('parkly-server', server);
    _hasServerOverride = true;
    api.server = server;
    notifyListeners();
  }

  Future<void> useAutomaticServer() async {
    await logout();
    await store.delete('parkly-server');
    _hasServerOverride = false;
    api.server = await discoverServer?.call() ?? _defaultServer;
    notifyListeners();
  }

  Future<void> saveProfile(Json value) async {
    user = await api.object('/auth/me', method: 'PATCH', body: value);
    notifyListeners();
  }
}

class ParkingData extends ChangeNotifier {
  final AuthState auth;
  List<Json> lots = [],
      spots = [],
      vehicles = [],
      reservations = [],
      prices = [];
  Json capacity = {}, alerts = {};
  int? lotId;
  bool loading = false;
  String? error;
  int _generation = 0;
  bool _disposed = false;
  Future<void>? _loadingTask;
  int? _loadingLot;
  Completer<void>? _queuedLoad;
  ParkingData(this.auth);
  ParkingApi get api => auth.api;

  Future<void> load({bool force = false}) {
    if (_disposed || auth.user == null) return Future<void>.value();
    final active = _loadingTask;
    if (active != null && (!force || _loadingLot == lotId)) {
      return (_queuedLoad ??= Completer<void>()).future;
    }
    final queued = _queuedLoad;
    _queuedLoad = null;
    final task = _startLoad();
    queued?.complete(task);
    return task;
  }

  Future<void> _startLoad() {
    final generation = ++_generation;
    _loadingLot = lotId;
    return _loadingTask = Future<void>.microtask(() => _refresh(generation));
  }

  bool _isCurrent(int generation) =>
      !_disposed && generation == _generation && auth.user != null;

  Future<void> _refresh(int generation) async {
    try {
      if (!_isCurrent(generation)) return;
      loading = true;
      error = null;
      notifyListeners();
      await _readData(generation);
    } catch (e) {
      if (_isCurrent(generation)) error = e.toString();
    } finally {
      if (!_disposed && generation == _generation) {
        final queued = _queuedLoad;
        _queuedLoad = null;
        if (queued != null && auth.user != null) {
          queued.complete(_startLoad());
        } else {
          queued?.complete();
          _loadingTask = null;
          loading = false;
          notifyListeners();
        }
      }
    }
  }

  Future<void> _readData(int generation) async {
    final loadedLots = await api.list('/parking-lots');
    if (!_isCurrent(generation)) return;
    lots = loadedLots;
    if (!lots.any((lot) => lot['id'] == lotId)) {
      lotId = lots.isEmpty ? null : lots.first['id'] as int;
      _clearLotData();
    }
    final activeLot = lotId;
    _loadingLot = activeLot;
    final vehiclePath = auth.staff ? '/dashboard-data/vehicles' : '/vehicles';
    if (activeLot == null) {
      final loadedVehicles = await api.list(vehiclePath);
      if (_isCurrent(generation)) vehicles = loadedVehicles;
      return;
    }
    final q = 'parking_lot_id=$activeLot';
    final result = await Future.wait<dynamic>([
      api.parkingSnapshot(activeLot),
      api.list(vehiclePath),
      api.list(
        auth.staff ? '/dashboard-data/reservations?$q' : '/reservations',
      ),
      api.list('/pricing-rules?$q'),
      auth.staff
          ? api.object('/alerts?$q&status=OPEN&limit=5')
          : Future<Json>.value({}),
    ]);
    if (!_isCurrent(generation)) return;
    final parking = result[0] as Json;
    spots = List<Json>.from(parking['spots'] as List);
    capacity = parking['capacity'] as Json;
    vehicles = result[1] as List<Json>;
    final ids = spots.map((s) => s['id']).toSet();
    reservations = (result[2] as List<Json>)
        .where((r) => ids.contains(r['parking_spot_id']))
        .toList();
    prices = result[3] as List<Json>;
    alerts = result[4] as Json;
  }

  void _clearLotData() {
    spots = [];
    reservations = [];
    prices = [];
    capacity = {};
    alerts = {};
  }

  void chooseLot(int id) {
    if (id == lotId) return;
    lotId = id;
    _clearLotData();
    unawaited(load(force: true));
  }

  Json? vehicle(int id) => vehicles.where((v) => v['id'] == id).firstOrNull;
  Json? spot(int? id) => spots.where((s) => s['id'] == id).firstOrNull;
  List<Json> get ownVehicles =>
      vehicles.where((v) => v['user_id'] == auth.user?['id']).toList();
  @override
  void dispose() {
    _disposed = true;
    _generation++;
    _queuedLoad?.complete();
    _queuedLoad = null;
    super.dispose();
  }
}
