import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'api.dart';

class RealtimeConnection {
  final ParkingApi api;
  final void Function() onChanged;
  WebSocketChannel? _socket;
  Timer? _retry, _debounce, _heartbeat;
  bool _active = false;
  int _generation = 0;
  RealtimeConnection(this.api, this.onChanged);

  void start() {
    if (_active) return;
    _active = true;
    unawaited(_connect(++_generation));
  }

  Future<void> _connect(int generation) async {
    if (!_active || generation != _generation || api.token == null) return;
    final uri = Uri.parse(api.server).replace(
      scheme: api.server.startsWith('https:') ? 'wss' : 'ws',
      path: '/ws/events',
    );
    WebSocketChannel? pending;
    try {
      final socket = WebSocketChannel.connect(uri);
      pending = socket;
      _socket = socket;
      _watch(socket, generation, timeout: const Duration(seconds: 10));
      await socket.ready;
      if (!_active || generation != _generation || _socket != socket) {
        _close(socket);
        return;
      }
      socket.sink.add(jsonEncode({'token': api.token}));
      _watch(socket, generation);
      String? revision;
      socket.stream.listen(
        (event) {
          if (!_active || generation != _generation || _socket != socket) {
            return;
          }
          try {
            final message = jsonDecode(event as String) as Json;
            final kind = message['type'];
            if (!['ready', 'invalidate', 'ping'].contains(kind)) return;
            _watch(socket, generation);
            if (kind == 'ping') socket.sink.add('pong');
            final version = message['revision'];
            final changed = version is String && version != revision;
            if (version is String) revision = version;
            if ((kind == 'ready' ||
                    changed ||
                    (kind == 'invalidate' && version is! String)) &&
                _debounce == null) {
              _debounce = Timer(const Duration(milliseconds: 250), () {
                _debounce = null;
                onChanged();
              });
            }
          } catch (_) {
            /* Ignore malformed notifications; REST remains authoritative. */
          }
        },
        onDone: () =>
            _lost(socket, generation, reconnect: socket.closeCode != 1008),
        onError: (Object _) => _lost(socket, generation),
      );
    } catch (_) {
      if (pending == null) {
        _reconnect(generation);
      } else {
        _lost(pending, generation);
      }
    }
  }

  void _watch(
    WebSocketChannel socket,
    int generation, {
    Duration timeout = const Duration(seconds: 45),
  }) {
    _heartbeat?.cancel();
    _heartbeat = Timer(timeout, () => _lost(socket, generation));
  }

  void _lost(WebSocketChannel socket, int generation, {bool reconnect = true}) {
    if (generation != _generation || _socket != socket) return;
    _heartbeat?.cancel();
    _socket = null;
    _close(socket);
    if (reconnect) _reconnect(generation);
  }

  void _close(WebSocketChannel? socket) {
    if (socket != null) {
      unawaited(socket.sink.close().catchError((Object _) {}));
    }
  }

  void _reconnect(int generation) {
    if (!_active || generation != _generation) return;
    _retry?.cancel();
    _retry = Timer(
      const Duration(seconds: 3),
      () => unawaited(_connect(generation)),
    );
  }

  void stop() {
    _active = false;
    _generation++;
    _retry?.cancel();
    _debounce?.cancel();
    _heartbeat?.cancel();
    _debounce = null;
    _close(_socket);
    _socket = null;
  }
}
