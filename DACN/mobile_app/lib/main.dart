import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'api.dart';
import 'auth_views.dart';
import 'backend_connection.dart';
import 'common.dart';
import 'screens.dart';
import 'realtime.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('vi_VN');
  const configuredServer = String.fromEnvironment('API_URL');
  final androidAutomatic =
      configuredServer.isEmpty &&
      !kIsWeb &&
      defaultTargetPlatform == TargetPlatform.android;
  final auth = AuthState(
    api: ParkingApi(
      server: configuredServer.isEmpty
          ? defaultBackend
          : normalizeServer(configuredServer),
    ),
    store: SecureSessionStore(),
    discoverServer: androidAutomatic ? findAndroidBackend : null,
  );
  runApp(ParklyApp(auth: auth));
  unawaited(auth.boot());
}

class ParklyApp extends StatefulWidget {
  final AuthState auth;
  const ParklyApp({super.key, required this.auth});
  @override
  State<ParklyApp> createState() => _ParklyAppState();
}

class _ParklyAppState extends State<ParklyApp> {
  final navigator = GlobalKey<NavigatorState>();
  AuthState get auth => widget.auth;
  @override
  void initState() {
    super.initState();
    auth.addListener(sessionChanged);
  }

  void sessionChanged() {
    if (auth.user == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && auth.user == null) {
          navigator.currentState?.popUntil((route) => route.isFirst);
        }
      });
    }
  }

  @override
  void dispose() {
    auth.removeListener(sessionChanged);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: navigator,
    title: 'Parkly',
    debugShowCheckedModeBanner: false,
    locale: const Locale('vi'),
    supportedLocales: const [Locale('vi'), Locale('en')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: forest,
        primary: forest,
        surface: Colors.white,
      ),
      scaffoldBackgroundColor: canvas,
      appBarTheme: const AppBarTheme(
        backgroundColor: canvas,
        surfaceTintColor: Colors.transparent,
        centerTitle: false,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 15,
          vertical: 16,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFDDE5D9)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: Color(0xFFDDE5D9)),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
    ),
    home: ListenableBuilder(
      listenable: auth,
      builder: (context, _) {
        if (auth.booting) {
          return const Scaffold(body: Center(child: Brand(size: 64)));
        }
        if (auth.bootError != null) {
          return Scaffold(
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Brand(size: 64),
                    const SizedBox(height: 30),
                    ErrorNotice(auth.bootError!),
                    PrimaryButton('Kết nối lại', onPressed: () => auth.boot()),
                    TextButton(
                      onPressed: () => auth.logout(),
                      child: const Text('Về đăng nhập'),
                    ),
                  ],
                ),
              ),
            ),
          );
        }
        if (auth.user == null) return AuthScreen(auth: auth);
        return HomeShell(
          key: ValueKey(
            '${auth.api.server}:${auth.user!['id']}:${auth.revision}',
          ),
          auth: auth,
        );
      },
    ),
  );
}

class HomeShell extends StatefulWidget {
  final AuthState auth;
  const HomeShell({super.key, required this.auth});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  late final ParkingData data;
  late final Timer timer;
  late final RealtimeConnection realtime;
  int selected = 0;
  bool visible = true;
  final titles = ['Tổng quan', 'Bãi xe', 'Đặt chỗ', 'Phương tiện', 'Tài khoản'];
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    data = ParkingData(widget.auth);
    realtime = RealtimeConnection(data.api, () => unawaited(data.load()));
    realtime.start();
    unawaited(data.load());
    timer = Timer.periodic(const Duration(seconds: 15), (_) {
      if (visible) unawaited(data.load());
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    visible = state == AppLifecycleState.resumed;
    if (visible) {
      realtime.start();
      unawaited(data.load());
    } else {
      realtime.stop();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    timer.cancel();
    realtime.stop();
    data.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: data,
    builder: (context, _) => Scaffold(
      appBar: AppBar(
        title: const Brand(size: 37),
        actions: [
          IconButton(
            tooltip: 'Làm mới',
            onPressed: data.loading ? null : () => data.load(),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => data.load(force: true),
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      titles[selected],
                      style: const TextStyle(
                        fontSize: 27,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF233F32),
                      ),
                    ),
                  ),
                  if (data.loading)
                    const SizedBox(
                      width: 17,
                      height: 17,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                ],
              ),
              const SizedBox(height: 14),
              if (data.lots.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: DropdownButtonFormField<int>(
                    key: ValueKey(data.lotId),
                    initialValue: data.lotId,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'Bãi xe đang xem',
                      prefixIcon: Icon(Icons.location_on_outlined),
                    ),
                    items: data.lots
                        .map(
                          (l) => DropdownMenuItem(
                            value: l['id'] as int,
                            child: Text(
                              l['name'] as String,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: (v) {
                      if (v != null) data.chooseLot(v);
                    },
                  ),
                ),
              if (data.error != null)
                ErrorNotice(
                  '${data.error}\nDữ liệu đang hiển thị có thể là lần tải trước.',
                ),
              if (widget.auth.staff && (data.alerts['open_count'] ?? 0) > 0)
                Surface(
                  padding: const EdgeInsets.all(12),
                  child: ListTile(
                    leading: const Icon(
                      Icons.warning_amber_rounded,
                      color: Colors.deepOrange,
                    ),
                    title: Text('${data.alerts['open_count']} sự cố đang mở'),
                    subtitle: const Text('Xem cảnh báo và nhật ký'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => openScreen(context, AlertsScreen(data: data)),
                  ),
                ),
              if (data.lots.isEmpty && !data.loading && selected < 3)
                const EmptyMessage(
                  'Chưa có bãi xe. Quản trị viên cần cấu hình bãi trên hệ thống.',
                ),
              switch (selected) {
                0 => OverviewTab(
                  data: data,
                  onParking: () => setState(() => selected = 1),
                  onVehicles: () => setState(() => selected = 3),
                ),
                1 => ParkingTab(
                  key: ValueKey('parking-${data.lotId}'),
                  data: data,
                ),
                2 => ReservationsTab(data: data),
                3 => VehiclesTab(data: data),
                _ => ProfileTab(auth: widget.auth, data: data),
              },
            ],
          ),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selected,
        onDestinationSelected: (v) => setState(() => selected = v),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        indicatorColor: mint,
        backgroundColor: Colors.white,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home_rounded),
            label: 'Trang chủ',
          ),
          NavigationDestination(
            icon: Icon(Icons.local_parking_outlined),
            label: 'Bãi xe',
          ),
          NavigationDestination(
            icon: Icon(Icons.event_available_outlined),
            label: 'Đặt chỗ',
          ),
          NavigationDestination(
            icon: Icon(Icons.directions_car_outlined),
            label: 'Xe của tôi',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline_rounded),
            label: 'Tài khoản',
          ),
        ],
      ),
    ),
  );
}
