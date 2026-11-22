import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

const localBackend = 'http://127.0.0.1:8001';
const _androidBackend = MethodChannel('vn.parkly/backend');

String get defaultBackend {
  if (kIsWeb && !['localhost', '127.0.0.1', '::1'].contains(Uri.base.host)) {
    return Uri.base.origin;
  }
  return localBackend;
}

Future<String?> findAndroidBackend() async {
  final client = http.Client();
  try {
    if (await _ready(client, localBackend)) return localBackend;

    List<String> hosts;
    try {
      hosts =
          await _androidBackend.invokeListMethod<String>('developmentHosts') ??
          const [];
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
    final candidates = hosts.map((host) => 'http://$host:8001').toList();
    final available = await Future.wait(
      candidates.map((server) => _ready(client, server)),
    );
    final first = available.indexOf(true);
    return first < 0 ? null : candidates[first];
  } finally {
    client.close();
  }
}

Future<bool> _ready(http.Client client, String server) async {
  try {
    final request = http.Request('GET', Uri.parse('$server/health/ready'))
      ..followRedirects = false;
    final response = await client
        .send(request)
        .then(http.Response.fromStream)
        .timeout(const Duration(seconds: 1));
    if (response.statusCode != 200) return false;
    final data = jsonDecode(response.body);
    return data is Map &&
        data['service'] == 'parkly' &&
        data['status'] == 'ready';
  } on TimeoutException {
    return false;
  } on http.ClientException {
    return false;
  } on FormatException {
    return false;
  }
}
