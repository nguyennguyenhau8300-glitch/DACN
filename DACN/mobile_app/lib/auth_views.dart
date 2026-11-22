import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'api.dart';
import 'common.dart';

class AuthScreen extends StatefulWidget {
  final AuthState auth;
  const AuthScreen({super.key, required this.auth});
  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final form = GlobalKey<FormState>();
  final email = TextEditingController(),
      password = TextEditingController(),
      name = TextEditingController(),
      hometown = TextEditingController(),
      plate = TextEditingController();
  bool register = false, busy = false, created = false;
  DateTime? birthday;
  String type = 'MOTORBIKE', energy = 'GASOLINE';
  String? error;
  @override
  void dispose() {
    for (final c in [email, password, name, hometown, plate]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> submit() async {
    if (!form.currentState!.validate()) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      if (register && !created) {
        await widget.auth.api.object(
          '/auth/register',
          method: 'POST',
          authenticated: false,
          body: {
            'full_name': name.text.trim(),
            'date_of_birth': DateFormat('yyyy-MM-dd').format(birthday!),
            'hometown': hometown.text.trim(),
            'email': email.text.trim(),
            'password': password.text,
            'vehicle': {
              'license_plate': plate.text.trim().toUpperCase(),
              'vehicle_type': type,
              'energy_type': energy,
            },
          },
        );
        created = true;
        if (mounted) setState(() => register = false);
      }
      await widget.auth.login(email.text, password.text);
    } catch (e) {
      if (mounted) {
        setState(
          () => error = created
              ? 'Tài khoản đã tạo. Hãy đăng nhập lại bằng email và mật khẩu vừa nhập.\n$e'
              : e.toString(),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      actions: [
        IconButton(
          tooltip: 'Cấu hình máy chủ',
          icon: const Icon(Icons.settings_outlined),
          onPressed: busy
              ? null
              : () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => ServerScreen(auth: widget.auth),
                  ),
                ),
        ),
      ],
    ),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 500),
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 30),
            child: Form(
              key: form,
              child: AutofillGroup(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Brand(size: 62),
                    const SizedBox(height: 26),
                    Text(
                      register ? 'Tạo tài khoản' : 'Chào bạn,',
                      style: const TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.w800,
                        color: forest,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      register
                          ? 'Đăng ký thông tin và xe để đặt chỗ.'
                          : 'Một chỗ đỗ an tâm cho hành trình của bạn.',
                      style: const TextStyle(
                        color: Color(0xFF7A8D7B),
                        height: 1.6,
                      ),
                    ),
                    const SizedBox(height: 28),
                    if (register) ...[
                      LabeledInput('Họ và tên', name, maxLength: 100),
                      DateOfBirthField(
                        value: birthday,
                        onChanged: (v) => setState(() => birthday = v),
                      ),
                      LabeledInput('Quê quán', hometown, maxLength: 200),
                    ],
                    TextFormField(
                      controller: email,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.username],
                      decoration: const InputDecoration(
                        labelText: 'Email',
                        hintText: 'ban@example.com',
                      ),
                      validator: (v) =>
                          v == null ||
                              !RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
                                  .hasMatch(v.trim())
                          ? 'Nhập email hợp lệ'
                          : null,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: password,
                      obscureText: true,
                      autocorrect: false,
                      enableSuggestions: false,
                      autofillHints: [
                        register
                            ? AutofillHints.newPassword
                            : AutofillHints.password,
                      ],
                      decoration: const InputDecoration(labelText: 'Mật khẩu'),
                      validator: (v) => v == null || v.length < 6
                          ? 'Mật khẩu cần ít nhất 6 ký tự'
                          : null,
                    ),
                    const SizedBox(height: 18),
                    if (register) ...[
                      const Divider(height: 28),
                      const Text(
                        'Xe đăng ký',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 16),
                      LabeledInput(
                        'Biển số xe',
                        plate,
                        hint: plateExample(type),
                        maxLength: 20,
                      ),
                      DropdownButtonFormField<String>(
                        initialValue: type,
                        decoration: const InputDecoration(labelText: 'Loại xe'),
                        items: const [
                          DropdownMenuItem(
                            value: 'MOTORBIKE',
                            child: Text('Xe máy'),
                          ),
                          DropdownMenuItem(value: 'CAR', child: Text('Ô tô')),
                        ],
                        onChanged: (v) => setState(() => type = v!),
                      ),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                        initialValue: energy,
                        decoration: const InputDecoration(
                          labelText: 'Nguồn năng lượng',
                        ),
                        items: const [
                          DropdownMenuItem(
                            value: 'GASOLINE',
                            child: Text('Xăng'),
                          ),
                          DropdownMenuItem(
                            value: 'ELECTRIC',
                            child: Text('Điện'),
                          ),
                        ],
                        onChanged: (v) => setState(() => energy = v!),
                      ),
                      const SizedBox(height: 20),
                    ],
                    if (error != null) ErrorNotice(error!),
                    PrimaryButton(
                      register ? 'Tạo tài khoản' : 'Đăng nhập',
                      busy: busy,
                      onPressed: submit,
                      icon: Icons.arrow_forward_rounded,
                    ),
                    const SizedBox(height: 12),
                    Center(
                      child: TextButton(
                        onPressed: busy
                            ? null
                            : () => setState(() {
                                register = !register;
                                error = null;
                                created = false;
                              }),
                        child: Text(
                          register
                              ? 'Đã có tài khoản? Đăng nhập'
                              : 'Chưa có tài khoản? Đăng ký',
                        ),
                      ),
                    ),
                    Center(
                      child: TextButton.icon(
                        onPressed: busy
                            ? null
                            : () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) =>
                                      ServerScreen(auth: widget.auth),
                                ),
                              ),
                        icon: const Icon(Icons.dns_outlined, size: 16),
                        label: const Text('Địa chỉ kết nối backend'),
                      ),
                    ),
                    const SizedBox(height: 14),
                    const Center(
                      child: Text(
                        'PARKLY · SMART PARKING',
                        style: TextStyle(
                          fontSize: 10,
                          letterSpacing: 2,
                          color: Color(0xFF94A28E),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

class ServerScreen extends StatefulWidget {
  final AuthState auth;
  const ServerScreen({super.key, required this.auth});
  @override
  State<ServerScreen> createState() => _ServerScreenState();
}

class _ServerScreenState extends State<ServerScreen> {
  late final TextEditingController server;
  bool busy = false;
  String? error, message;
  @override
  void initState() {
    super.initState();
    server = TextEditingController(text: widget.auth.api.server);
  }

  @override
  void dispose() {
    server.dispose();
    super.dispose();
  }

  Future<void> test() async {
    setState(() {
      busy = true;
      error = null;
      message = null;
    });
    ParkingApi? probe;
    try {
      probe = ParkingApi(server: normalizeServer(server.text));
      await probe.object('/health/ready', authenticated: false);
      if (mounted) setState(() => message = 'Backend và database sẵn sàng.');
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      probe?.client.close();
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.auth.changeServer(server.text);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> automatic() async {
    setState(() {
      busy = true;
      error = null;
      message = null;
    });
    try {
      await widget.auth.useAutomaticServer();
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Kết nối máy chủ')),
    body: ListView(
      padding: const EdgeInsets.all(22),
      children: [
        const Text(
          'Dùng cùng hệ thống Parkly',
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 12),
        const Text(
          'Parkly tự kết nối với backend chạy bằng python main.py. Nhập địa chỉ riêng khi dùng máy chủ khác.',
          style: TextStyle(height: 1.7, color: Color(0xFF738371)),
        ),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: busy ? null : automatic,
          icon: const Icon(Icons.bolt),
          label: const Text('Dùng kết nối tự động'),
        ),
        const SizedBox(height: 22),
        LabeledInput('Địa chỉ backend', server, keyboard: TextInputType.url),
        if (error != null) ErrorNotice(error!),
        if (message != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 18),
            child: Text(message!, style: const TextStyle(color: forest)),
          ),
        OutlinedButton.icon(
          onPressed: busy ? null : test,
          icon: const Icon(Icons.wifi_find),
          label: const Text('Kiểm tra kết nối'),
        ),
        const SizedBox(height: 12),
        PrimaryButton('Lưu địa chỉ', onPressed: save, busy: busy),
        const SizedBox(height: 14),
        const Text(
          'Đổi máy chủ sẽ đăng xuất phiên hiện tại.',
          style: TextStyle(color: Color(0xFF7B8D79)),
        ),
      ],
    ),
  );
}
