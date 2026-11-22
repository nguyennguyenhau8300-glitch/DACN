import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'api.dart';
import 'auth_views.dart';
import 'common.dart';
import 'operations.dart';
import 'research_screens.dart';
export 'operations.dart';

void openScreen(BuildContext context, Widget screen) =>
    Navigator.push(context, MaterialPageRoute(builder: (_) => screen));

class OverviewTab extends StatelessWidget {
  final ParkingData data;
  final VoidCallback onParking, onVehicles;
  const OverviewTab({
    super.key,
    required this.data,
    required this.onParking,
    required this.onVehicles,
  });
  @override
  Widget build(BuildContext context) {
    final groups = (data.capacity['groups'] as List? ?? []).cast<Json>();
    final free = groups.fold<int>(
      0,
      (n, g) => n + (g['available_for_booking'] as int),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(22),
          margin: const EdgeInsets.only(bottom: 18),
          decoration: BoxDecoration(
            color: forest,
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Xin chào, ${data.auth.user!['full_name']}',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              const Text(
                'Chỗ đỗ sẵn sàng.\nHành trình nhẹ nhàng.',
                style: TextStyle(
                  fontSize: 26,
                  height: 1.25,
                  fontWeight: FontWeight.w800,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 22),
              Row(
                children: [
                  Text(
                    '$free',
                    style: const TextStyle(
                      fontSize: 44,
                      fontWeight: FontWeight.w800,
                      color: mint,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'chỗ có thể đặt\ntrong bãi đang xem',
                      style: TextStyle(color: Colors.white70, height: 1.5),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: onParking,
                style: FilledButton.styleFrom(
                  backgroundColor: mint,
                  foregroundColor: forest,
                ),
                child: const Text('Tìm chỗ đỗ'),
              ),
            ],
          ),
        ),
        Row(
          children: [
            Expanded(
              child: _metric(
                'Đang có xe',
                data.spots.where((s) => s['status'] == 'OCCUPIED').length,
                Icons.directions_car_outlined,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _metric(
                'Xe của bạn',
                data.ownVehicles.length,
                Icons.garage_outlined,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        const Text(
          'Các khu đỗ xe',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 14),
        for (final g in groups)
          Surface(
            child: Row(
              children: [
                Icon(
                  g['vehicle_type'] == 'CAR'
                      ? Icons.directions_car
                      : Icons.two_wheeler,
                  color: forest,
                  size: 30,
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        g['label'] as String,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        '${g['configured_spots']} ô · ${g['ready_charging_points']} điểm sạc sẵn sàng',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFF7D8F79),
                        ),
                      ),
                    ],
                  ),
                ),
                Text(
                  '${g['available_for_booking']}',
                  style: const TextStyle(
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                    color: forest,
                  ),
                ),
              ],
            ),
          ),
        _action(
          Icons.search,
          'Tìm bãi xe',
          'Tra cứu theo tên hoặc địa chỉ',
          () => openScreen(context, FindLotScreen(data: data)),
        ),
        _action(
          Icons.route_outlined,
          'Gợi ý ô & đường đi',
          'Chọn ô phù hợp và xem đường đến ô',
          () => openScreen(context, RoutingScreen(data: data)),
        ),
        _action(
          Icons.qr_code_2,
          'Thanh toán thử nghiệm',
          'QR mô phỏng, không chuyển tiền thật',
          () => openScreen(context, CheckoutScreen(data: data)),
        ),
        _action(
          Icons.history_rounded,
          'Lịch sử gửi xe & thanh toán',
          'Theo dõi lượt gửi và chi phí',
          () => openScreen(context, HistoryScreen(data: data)),
        ),
        _action(
          Icons.add_road,
          'Đăng ký phương tiện',
          'Lưu xe để đặt chỗ nhanh hơn',
          onVehicles,
        ),
        if (data.auth.staff) ...[
          _action(
            Icons.login_rounded,
            'Ghi nhận xe vào',
            'Nhận xe theo biển số đã đăng ký',
            () => openScreen(context, BookingScreen(data: data, checkin: true)),
          ),
          _action(
            Icons.document_scanner_outlined,
            'Nhận diện biển số AI',
            'Chụp ảnh hoặc chọn từ thư viện',
            () => openScreen(context, AiScreen(data: data)),
          ),
          _action(
            Icons.notifications_active_outlined,
            'Cảnh báo & sự cố',
            'Tiếp nhận và theo dõi lịch sử xử lý',
            () => openScreen(context, AlertsScreen(data: data)),
          ),
        ],
        if (data.prices.isNotEmpty)
          Surface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Phí gửi xe',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 10),
                for (final p in data.prices.where(
                  (p) => p['is_active'] == true,
                ))
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 7),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          vehicleName(p),
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        Text(
                          (p['time_bands'] as List? ?? []).isNotEmpty
                              ? 'Giá theo khung giờ: ${(p['time_bands'] as List).map((b) => "${(b['start_minute'] as num) ~/ 60}h–${(b['end_minute'] as num) / 60}h ${money(b['hourly_price'])}/giờ").join(' · ')}'
                              : '${money(p['first_hour_price'])} giờ đầu · ${money(p['additional_hour_price'])}/giờ tiếp theo',
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF7B8F77),
                          ),
                        ),
                      ],
                    ),
                  ),
                const Text(
                  'Phí gửi xe được tính khi xe ra. Chưa tính phí điện sạc.',
                  style: TextStyle(fontSize: 11, color: Color(0xFF7D8F79)),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _metric(String label, int value, IconData icon) => Surface(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: forest),
        const SizedBox(height: 10),
        Text(
          '$value',
          style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
        ),
        Text(label, style: const TextStyle(color: Color(0xFF7D8F79))),
      ],
    ),
  );
  Widget _action(IconData icon, String title, String sub, VoidCallback onTap) =>
      Surface(
        padding: const EdgeInsets.all(6),
        child: ListTile(
          leading: Icon(icon, color: forest),
          title: Text(
            title,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          subtitle: Text(sub, style: const TextStyle(fontSize: 12)),
          trailing: const Icon(Icons.chevron_right),
          onTap: onTap,
        ),
      );
}

class ParkingTab extends StatefulWidget {
  final ParkingData data;
  const ParkingTab({super.key, required this.data});
  @override
  State<ParkingTab> createState() => _ParkingTabState();
}

class _ParkingTabState extends State<ParkingTab> {
  int group = 0;
  bool availableOnly = false;
  final groups = [
    ['Tất cả', '', ''],
    ['Ô tô xăng', 'CAR', 'GASOLINE'],
    ['Ô tô điện', 'CAR', 'ELECTRIC'],
    ['Xe máy xăng', 'MOTORBIKE', 'GASOLINE'],
    ['Xe máy điện', 'MOTORBIKE', 'ELECTRIC'],
  ];
  @override
  Widget build(BuildContext context) {
    final rows = widget.data.spots
        .where(
          (s) =>
              (group == 0 ||
                  ((s['spot_type'] == 'DISABLED' ? 'CAR' : s['spot_type']) ==
                          groups[group][1] &&
                      s['energy_type'] == groups[group][2])) &&
              (!availableOnly || s['available_for_booking'] == true),
        )
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 7,
          runSpacing: 3,
          children: List.generate(
            groups.length,
            (i) => ChoiceChip(
              label: Text(groups[i][0]),
              selected: group == i,
              onSelected: (_) => setState(() => group = i),
            ),
          ),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Chỉ hiện chỗ có thể đặt'),
          value: availableOnly,
          onChanged: (v) => setState(() => availableOnly = v),
        ),
        Text(
          '${rows.length} ô đỗ',
          style: const TextStyle(color: Color(0xFF7B8D79)),
        ),
        const SizedBox(height: 12),
        if (rows.isEmpty && !widget.data.loading)
          const EmptyMessage('Không có ô phù hợp bộ lọc.'),
        LayoutBuilder(
          builder: (context, constraints) => Wrap(
            spacing: 10,
            runSpacing: 10,
            children: rows
                .map(
                  (s) => SizedBox(
                    width: (constraints.maxWidth - 10) / 2,
                    child: Material(
                      color: s['available_for_booking'] == true
                          ? Colors.white
                          : const Color(0xFFE9EEE7),
                      borderRadius: BorderRadius.circular(17),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(17),
                        onTap: () => details(context, s),
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    s['energy_type'] == 'ELECTRIC'
                                        ? Icons.ev_station_outlined
                                        : s['spot_type'] == 'CAR'
                                        ? Icons.directions_car_outlined
                                        : Icons.two_wheeler,
                                    size: 25,
                                    color: forest,
                                  ),
                                  const Spacer(),
                                  if (s['available_for_booking'] == true)
                                    const Icon(
                                      Icons.circle,
                                      size: 7,
                                      color: forest,
                                    ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              Text(
                                s['spot_code'] as String,
                                style: const TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                              const SizedBox(height: 5),
                              Text(
                                vehicleName(s),
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: Color(0xFF7B8D79),
                                ),
                              ),
                              const SizedBox(height: 9),
                              Text(
                                s['status'] == 'AVAILABLE' &&
                                        s['available_for_booking'] != true
                                    ? 'Chưa sẵn sàng'
                                    : statusNames[s['status']] ?? s['status'],
                                style: const TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ),
      ],
    );
  }

  void details(BuildContext context, Json spot) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (c) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Ô ${spot['spot_code']}',
                style: const TextStyle(
                  fontSize: 27,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 10),
              Text(vehicleName(spot)),
              const SizedBox(height: 16),
              StatusChip(spot['status'] as String),
              if (spot['energy_type'] == 'ELECTRIC') ...[
                const SizedBox(height: 16),
                Text(
                  '${spot['charger_type'] == 'SOCKET' ? 'Ổ cắm' : 'Trạm sạc'} · ${statusNames[spot['charger_status']] ?? spot['charger_status']}',
                ),
                if (spot['charging_power_kw'] != null)
                  Text('Công suất khai báo: ${spot['charging_power_kw']} kW'),
              ],
              const SizedBox(height: 20),
              if (spot['available_for_booking'] != true)
                const ErrorNotice(
                  'Ô đang được sử dụng, giữ chỗ hoặc chưa đủ điều kiện thiết bị/sạc để nhận xe mới.',
                ),
              PrimaryButton(
                'Đặt chỗ này',
                onPressed: spot['available_for_booking'] == true
                    ? () {
                        Navigator.pop(c);
                        openScreen(
                          context,
                          BookingScreen(data: widget.data, initialSpot: spot),
                        );
                      }
                    : null,
                icon: Icons.event_available_outlined,
              ),
              if (widget.data.auth.staff) ...[
                const SizedBox(height: 10),
                OutlinedButton(
                  onPressed: spot['available_for_booking'] == true
                      ? () {
                          Navigator.pop(c);
                          openScreen(
                            context,
                            BookingScreen(
                              data: widget.data,
                              initialSpot: spot,
                              checkin: true,
                            ),
                          );
                        }
                      : null,
                  child: const Text('Ghi nhận xe vào'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class BookingScreen extends StatefulWidget {
  final ParkingData data;
  final Json? initialSpot;
  final bool checkin;
  final int? initialVehicleId;
  const BookingScreen({
    super.key,
    required this.data,
    this.initialSpot,
    this.checkin = false,
    this.initialVehicleId,
  });
  @override
  State<BookingScreen> createState() => _BookingScreenState();
}

class _BookingScreenState extends State<BookingScreen> {
  int? vehicleId, spotId;
  late DateTime start, plannedDeparture;
  int advanceMinutes = bookingPolicyMinutes;
  int checkinMinutes = bookingPolicyMinutes;
  Duration clockOffset = Duration.zero;
  bool busy = false;
  bool scheduled = false, findingSpots = false;
  int searchVersion = 0;
  List<Json> slotOptions = [];
  String? slotError;
  String? error;
  @override
  void initState() {
    super.initState();
    start = vietnamNow().add(const Duration(minutes: 5));
    plannedDeparture = start.add(const Duration(hours: 1));
    spotId = widget.initialSpot?['id'] as int?;
    vehicleId = widget.initialVehicleId;
    if (!widget.checkin) unawaited(loadPolicy());
  }

  Future<void> loadPolicy() async {
    try {
      final policy = await widget.data.api.object('/reservations/policy');
      final serverTime = DateTime.tryParse('${policy['server_time']}Z');
      final advance = policy['max_advance_minutes'];
      final grace = policy['checkin_window_minutes'];
      if (!mounted || serverTime == null || advance is! int || grace is! int) {
        return;
      }
      setState(() {
        clockOffset = serverTime.difference(vietnamNow());
        advanceMinutes = advance;
        checkinMinutes = grace;
      });
    } catch (_) {
      // The form can preview the default policy until the server is reachable.
    }
  }

  DateTime bookingNow() => vietnamNow().add(clockOffset);

  bool validStart(DateTime candidate) {
    final current = bookingNow();
    return !candidate.isBefore(current) &&
        (scheduled ||
            !candidate.isAfter(current.add(Duration(minutes: advanceMinutes))));
  }

  DateTime get deadline {
    final grace = bookingExpiry(start, checkinMinutes);
    return scheduled && plannedDeparture.isBefore(grace)
        ? plannedDeparture
        : grace;
  }

  Json? get selected => widget.data.vehicle(vehicleId ?? -1);
  List<Json> get spots => scheduled
      ? slotOptions
      : widget.data.spots
            .where(
              (s) =>
                  s['available_for_booking'] == true &&
                  (selected == null || compatible(selected!, s)),
            )
            .toList();
  Future<void> findScheduledSpots() async {
    final version = ++searchVersion;
    final vehicle = selected;
    final lot = widget.data.lotId;
    final canSearch =
        scheduled &&
        vehicle != null &&
        lot != null &&
        validStart(start) &&
        plannedDeparture.isAfter(start);
    setState(() {
      slotOptions = [];
      slotError = null;
      findingSpots = canSearch;
    });
    if (!canSearch) return;
    final query = Uri(
      queryParameters: {
        'parking_lot_id': lot.toString(),
        'vehicle_type': vehicle['vehicle_type'] as String,
        'energy_type': vehicle['energy_type'] as String,
        'start_time': wallTime(start),
        'end_time': wallTime(plannedDeparture),
      },
    ).query;
    try {
      final rows = await widget.data.api.list(
        '/reservations/available-spots?$query',
      );
      if (mounted && version == searchVersion) {
        setState(() => slotOptions = rows);
      }
    } catch (e) {
      if (mounted && version == searchVersion) {
        setState(() => slotError = e.toString());
      }
    } finally {
      if (mounted && version == searchVersion) {
        setState(() => findingSpots = false);
      }
    }
  }

  Future<void> pickBookingTime({bool departure = false}) async {
    final earliest = departure ? start : bookingNow();
    final latest = scheduled
        ? DateTime.utc(9999, 12, 31, 23, 59)
        : earliest.add(Duration(minutes: advanceMinutes));
    final current = departure ? plannedDeparture : start;
    final initial = current.isBefore(earliest) || current.isAfter(latest)
        ? earliest
        : current;
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime(initial.year, initial.month, initial.day),
      firstDate: DateTime(earliest.year, earliest.month, earliest.day),
      lastDate: DateTime(latest.year, latest.month, latest.day),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: initial.hour, minute: initial.minute),
    );
    if (time != null && mounted) {
      final chosen = DateTime.utc(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
      setState(() {
        if (departure) {
          plannedDeparture = chosen;
        } else {
          start = chosen;
          if (scheduled && !plannedDeparture.isAfter(chosen)) {
            plannedDeparture = chosen.add(const Duration(hours: 1));
          }
        }
        error = !validStart(start)
            ? 'Chọn giờ đến trong khoảng cho phép.'
            : scheduled && !plannedDeparture.isAfter(start)
            ? 'Giờ rời bãi phải sau giờ bắt đầu.'
            : null;
      });
      if (scheduled) unawaited(findScheduledSpots());
    }
  }

  Future<void> save() async {
    if (vehicleId == null || spotId == null) {
      setState(() => error = 'Chọn phương tiện và ô đỗ phù hợp.');
      return;
    }
    if (!widget.checkin && !validStart(start)) {
      setState(() => error = 'Chọn giờ đến trong khoảng cho phép.');
      return;
    }
    if (scheduled &&
        (!plannedDeparture.isAfter(start) ||
            !spots.any((s) => s['id'] == spotId))) {
      setState(() => error = 'Chọn khung giờ và ô đỗ còn trống.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.data.api.object(
        widget.checkin ? '/parking-sessions/check-in' : '/reservations',
        method: 'POST',
        body: {
          'vehicle_id': vehicleId,
          'parking_spot_id': spotId,
          if (!widget.checkin) 'start_time': wallTime(start),
          if (scheduled) 'end_time': wallTime(plannedDeparture),
        },
      );
      await widget.data.load(force: true);
      if (mounted) {
        toast(
          context,
          widget.checkin
              ? 'Đã ghi nhận xe vào.'
              : scheduled
              ? 'Đã đặt ô theo khung giờ.'
              : 'Đã đặt và giữ chỗ.',
        );
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        setState(() => error = e.toString());
        if (scheduled && e is ApiError && e.status == 409) {
          unawaited(findScheduledSpots());
        }
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.data,
    builder: (context, _) {
      final vehicles = widget.data.vehicles;
      final candidates = spots;
      if (!vehicles.any((v) => v['id'] == vehicleId)) vehicleId = null;
      final visibleSpot = candidates.any((s) => s['id'] == spotId)
          ? spotId
          : null;
      if (!findingSpots) spotId = visibleSpot;
      final spotPicker = DropdownButtonFormField<int>(
        key: ValueKey('spot-$visibleSpot'),
        initialValue: visibleSpot,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Ô đỗ phù hợp'),
        items: candidates
            .map(
              (s) => DropdownMenuItem(
                value: s['id'] as int,
                child: Text('${s['spot_code']} · ${vehicleName(s)}'),
              ),
            )
            .toList(),
        onChanged: busy || findingSpots
            ? null
            : (value) => setState(() => spotId = value),
      );
      return Scaffold(
        appBar: AppBar(
          title: Text(widget.checkin ? 'Ghi nhận xe vào' : 'Đặt chỗ mới'),
        ),
        body: ListView(
          padding: const EdgeInsets.all(22),
          children: [
            const Text(
              'Chọn phương tiện và ô đỗ',
              style: TextStyle(fontSize: 23, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 20),
            DropdownButtonFormField<int>(
              key: ValueKey('vehicle-$vehicleId'),
              initialValue: vehicleId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Phương tiện'),
              items: vehicles
                  .map(
                    (v) => DropdownMenuItem(
                      value: v['id'] as int,
                      child: Text(
                        '${v['license_plate']} · ${vehicleName(v)}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(),
              onChanged: busy
                  ? null
                  : (id) {
                      setState(() => vehicleId = id);
                      if (scheduled) unawaited(findScheduledSpots());
                    },
            ),
            const SizedBox(height: 10),
            TextButton.icon(
              onPressed: busy
                  ? null
                  : () async {
                      await Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => VehicleForm(data: widget.data),
                        ),
                      );
                    },
              icon: const Icon(Icons.add),
              label: const Text('Đăng ký thêm xe'),
            ),
            const SizedBox(height: 12),
            if (!scheduled) spotPicker,
            if (!scheduled && candidates.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 16),
                child: Text(
                  'Chưa có ô phù hợp sẵn sàng. Hãy kiểm tra loại xe, trạng thái sạc và thiết bị.',
                ),
              ),
            if (!widget.checkin) ...[
              const SizedBox(height: 20),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Đặt theo khung giờ'),
                value: scheduled,
                onChanged: busy
                    ? null
                    : (enabled) {
                        setState(() {
                          scheduled = enabled;
                          error = null;
                          if (!validStart(start)) {
                            start = bookingNow().add(
                              const Duration(minutes: 5),
                            );
                          }
                          if (!plannedDeparture.isAfter(start)) {
                            plannedDeparture = start.add(
                              const Duration(hours: 1),
                            );
                          }
                        });
                        unawaited(findScheduledSpots());
                      },
              ),
              OutlinedButton.icon(
                onPressed: busy ? null : () => pickBookingTime(),
                icon: const Icon(Icons.calendar_month_outlined),
                label: Text('Bắt đầu: ${dateText(wallTime(start))}'),
              ),
              if (scheduled)
                OutlinedButton.icon(
                  onPressed: busy
                      ? null
                      : () => pickBookingTime(departure: true),
                  icon: const Icon(Icons.schedule_outlined),
                  label: Text(
                    'Rời bãi dự kiến: ${dateText(wallTime(plannedDeparture))}',
                  ),
                )
              else
                Text(
                  'Chọn giờ đến trong ${advanceMinutes ~/ 60} giờ tới. Ô được giữ ngay khi xác nhận.',
                ),
              const SizedBox(height: 16),
              Surface(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Tự hủy nếu chưa nhận xe',
                      style: TextStyle(color: Color(0xFF967335)),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      dateText(wallTime(deadline)),
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      scheduled
                          ? 'Nhận xe từ giờ bắt đầu, trong khung giờ đã chọn.'
                          : 'Nhận xe từ giờ bắt đầu. Hạn nhận xe là ${checkinMinutes ~/ 60} giờ sau giờ bắt đầu.',
                      style: const TextStyle(
                        fontSize: 12,
                        height: 1.6,
                        color: Color(0xFF7E8F7A),
                      ),
                    ),
                  ],
                ),
              ),
              if (scheduled) ...[
                const SizedBox(height: 16),
                spotPicker,
                if (slotError != null) ErrorNotice(slotError!),
                if (findingSpots) const LinearProgressIndicator(),
                if (vehicleId == null)
                  const Text('Chọn phương tiện để tìm ô theo khung giờ.'),
                if (!findingSpots &&
                    slotError == null &&
                    vehicleId != null &&
                    candidates.isEmpty)
                  const Text('Chưa có ô phù hợp trong khung giờ đã chọn.'),
              ],
            ],
            const SizedBox(height: 20),
            if (error != null) ErrorNotice(error!),
            PrimaryButton(
              widget.checkin ? 'Ghi nhận xe vào' : 'Xác nhận đặt chỗ',
              busy: busy,
              onPressed: vehicleId != null && spotId != null ? save : null,
            ),
          ],
        ),
      );
    },
  );
}

class ReservationsTab extends StatefulWidget {
  final ParkingData data;
  const ReservationsTab({super.key, required this.data});
  @override
  State<ReservationsTab> createState() => _ReservationsTabState();
}

class _ReservationsTabState extends State<ReservationsTab> {
  int? busy;
  String? error;

  String phase(Json row) => (row['arrival_status'] ?? row['status']) as String;
  Future<void> action(Json row, bool cancel) async {
    if (!await confirm(
      context,
      cancel ? 'Hủy đặt chỗ?' : 'Nhận xe theo đặt chỗ?',
      cancel ? 'Chỗ sẽ được giải phóng theo trạng thái thực tế.' : 'Backend kiểm tra thời gian đặt và trạng thái ô trước khi ghi nhận.',
    )) {
      return;
    }
    setState(() {
      busy = row['id'] as int;
      error = null;
    });
    try {
      await widget.data.api.object(
        cancel
            ? '/reservations/${row['id']}/cancel'
            : '/parking-sessions/check-in',
        method: cancel ? 'PATCH' : 'POST',
        body: cancel
            ? null
            : {
                'vehicle_id': row['vehicle_id'],
                'parking_spot_id': row['parking_spot_id'],
                'reservation_id': row['id'],
              },
      );
      await widget.data.load(force: true);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = null);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    children: [
      PrimaryButton(
        'Đặt chỗ mới',
        icon: Icons.add,
        onPressed: widget.data.lotId == null
            ? null
            : () => openScreen(context, BookingScreen(data: widget.data)),
      ),
      const SizedBox(height: 18),
      if (error != null) ErrorNotice(error!),
      if (widget.data.reservations.isEmpty && !widget.data.loading)
        const EmptyMessage('Chưa có đặt chỗ trong bãi này.'),
      for (final r in widget.data.reservations)
        Surface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 10,
                runSpacing: 8,
                alignment: WrapAlignment.spaceBetween,
                children: [
                  Text(
                    widget.data.vehicle(
                          r['vehicle_id'] as int,
                        )?['license_plate'] ??
                        'Xe #${r['vehicle_id']}',
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  StatusChip(
                    phase(r) == 'EXPIRED' ? 'EXPIRED' : r['status'] as String,
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                'Đặt chỗ #${r['id']} · Ô ${widget.data.spot(r['parking_spot_id'] as int)?['spot_code'] ?? r['parking_spot_id']}',
              ),
              const SizedBox(height: 9),
              Text('Bắt đầu: ${dateText(r['start_time'])}'),
              if (r['end_time'] != null)
                Text('Rời bãi dự kiến: ${dateText(r['end_time'])}'),
              Text('Hạn nhận xe: ${dateText(r['expiry_time'])}'),
              if (bookingArrivalLabels[phase(r)] case final label?) Text(label),
              if ([
                'PENDING',
                'CONFIRMED',
                'UPCOMING',
                'READY',
              ].contains(phase(r))) ...[
                const SizedBox(height: 14),
                if (widget.data.auth.staff &&
                    ['READY', 'CONFIRMED'].contains(phase(r)))
                  PrimaryButton(
                    'Nhận xe',
                    busy: busy == r['id'],
                    onPressed: busy == null ? () => action(r, false) : null,
                  ),
                if (widget.data.auth.admin ||
                    r['user_id'] == widget.data.auth.user!['id'])
                  TextButton(
                    onPressed: busy == null ? () => action(r, true) : null,
                    child: const Text('Hủy đặt chỗ'),
                  ),
              ],
            ],
          ),
        ),
    ],
  );
}

class VehiclesTab extends StatelessWidget {
  final ParkingData data;
  const VehiclesTab({super.key, required this.data});
  @override
  Widget build(BuildContext context) => Column(
    children: [
      PrimaryButton(
        data.auth.staff ? 'Đăng ký phương tiện' : 'Thêm xe của tôi',
        icon: Icons.add,
        onPressed: () => openScreen(context, VehicleForm(data: data)),
      ),
      const SizedBox(height: 18),
      if (data.vehicles.isEmpty && !data.loading)
        const EmptyMessage(
          'Bạn chưa có xe. Thêm biển số và loại xe để đặt chỗ.',
        ),
      for (final v in data.vehicles)
        Surface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    v['vehicle_type'] == 'CAR'
                        ? Icons.directions_car
                        : Icons.two_wheeler,
                    size: 32,
                    color: forest,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          v['license_plate'] as String,
                          style: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        Text(
                          vehicleName(v),
                          style: const TextStyle(color: Color(0xFF7E8F7A)),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                v['user_id'] == data.auth.user!['id']
                    ? 'Xe của bạn'
                    : v['user_id'] == null
                    ? 'Khách vãng lai'
                    : 'Tài khoản chủ xe #${v['user_id']}',
                style: const TextStyle(fontSize: 12, color: forest),
              ),
              if (v['brand'] != null || v['color'] != null)
                Text('${v['brand'] ?? ''} ${v['color'] ?? ''}'.trim()),
              if (v['user_id'] == data.auth.user!['id'])
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => openScreen(
                      context,
                      VehicleForm(data: data, vehicle: v),
                    ),
                    child: const Text('Chỉnh sửa xe'),
                  ),
                ),
            ],
          ),
        ),
    ],
  );
}

class VehicleForm extends StatefulWidget {
  final ParkingData data;
  final Json? vehicle;
  const VehicleForm({super.key, required this.data, this.vehicle});
  @override
  State<VehicleForm> createState() => _VehicleFormState();
}

class _VehicleFormState extends State<VehicleForm> {
  final form = GlobalKey<FormState>();
  late final TextEditingController plate, brand, color;
  final email = TextEditingController();
  late String type, energy;
  String target = 'own';
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    final v = widget.vehicle ?? {};
    plate = TextEditingController(text: v['license_plate'] as String?);
    brand = TextEditingController(text: v['brand'] as String?);
    color = TextEditingController(text: v['color'] as String?);
    type = v['vehicle_type'] ?? 'MOTORBIKE';
    energy = v['energy_type'] ?? 'GASOLINE';
  }

  @override
  void dispose() {
    for (final c in [plate, brand, color, email]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final staffTarget =
          widget.data.auth.staff && target != 'own' && widget.vehicle == null;
      await widget.data.api.object(
        staffTarget
            ? '/dashboard-data/vehicles'
            : '/vehicles${widget.vehicle == null ? '' : '/${widget.vehicle!['id']}'}',
        method: widget.vehicle == null ? 'POST' : 'PUT',
        body: {
          'license_plate': plate.text.trim().toUpperCase(),
          'vehicle_type': type,
          'energy_type': energy,
          'brand': brand.text.trim().isEmpty ? null : brand.text.trim(),
          'color': color.text.trim().isEmpty ? null : color.text.trim(),
          if (staffTarget)
            'customer_email': target == 'account' ? email.text.trim() : null,
        },
      );
      await widget.data.load(force: true);
      if (mounted) {
        toast(context, 'Đã lưu phương tiện.');
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.vehicle == null
            ? 'Đăng ký phương tiện'
            : 'Chỉnh sửa phương tiện',
      ),
    ),
    body: Form(
      key: form,
      child: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          if (widget.data.auth.staff && widget.vehicle == null) ...[
            DropdownButtonFormField<String>(
              initialValue: target,
              decoration: const InputDecoration(labelText: 'Đăng ký cho'),
              items: const [
                DropdownMenuItem(value: 'own', child: Text('Xe của tôi')),
                DropdownMenuItem(value: 'guest', child: Text('Khách vãng lai')),
                DropdownMenuItem(
                  value: 'account',
                  child: Text('Khách đã có tài khoản'),
                ),
              ],
              onChanged: busy ? null : (v) => setState(() => target = v!),
            ),
            const SizedBox(height: 16),
            if (target == 'account')
              LabeledInput(
                'Email tài khoản khách hàng',
                email,
                keyboard: TextInputType.emailAddress,
              ),
          ],
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
              DropdownMenuItem(value: 'MOTORBIKE', child: Text('Xe máy')),
              DropdownMenuItem(value: 'CAR', child: Text('Ô tô')),
            ],
            onChanged: busy ? null : (v) => setState(() => type = v!),
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            initialValue: energy,
            decoration: const InputDecoration(labelText: 'Nguồn năng lượng'),
            items: const [
              DropdownMenuItem(value: 'GASOLINE', child: Text('Xăng')),
              DropdownMenuItem(value: 'ELECTRIC', child: Text('Điện')),
            ],
            onChanged: busy ? null : (v) => setState(() => energy = v!),
          ),
          const SizedBox(height: 16),
          LabeledInput('Hãng xe', brand, required: false, maxLength: 50),
          LabeledInput('Màu sắc', color, required: false, maxLength: 50),
          if (widget.vehicle != null)
            const Padding(
              padding: EdgeInsets.only(bottom: 16),
              child: Text(
                'Xe đã có lịch sử gửi không đổi được biển số, loại xe và nguồn năng lượng.',
                style: TextStyle(fontSize: 12, color: Color(0xFF7E8F7A)),
              ),
            ),
          if (error != null) ErrorNotice(error!),
          PrimaryButton('Lưu phương tiện', busy: busy, onPressed: save),
        ],
      ),
    ),
  );
}

class ProfileTab extends StatelessWidget {
  final AuthState auth;
  final ParkingData data;
  const ProfileTab({super.key, required this.auth, required this.data});
  @override
  Widget build(BuildContext context) => Column(
    children: [
      Surface(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.account_circle_outlined, size: 55, color: forest),
            const SizedBox(height: 12),
            Text(
              auth.user!['full_name'],
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
            ),
            Text(auth.user!['email']),
            const SizedBox(height: 8),
            Text(
              roleNames[auth.user!['role']] ?? auth.user!['role'],
              style: const TextStyle(color: forest),
            ),
            const Divider(height: 28),
            Text('Ngày sinh: ${birthText(auth.user!['date_of_birth'])}'),
            const SizedBox(height: 10),
            Text('Quê quán: ${auth.user!['hometown'] ?? 'Chưa bổ sung'}'),
            const SizedBox(height: 16),
            PrimaryButton(
              'Sửa thông tin cá nhân',
              onPressed: () => openScreen(context, ProfileForm(auth: auth)),
            ),
          ],
        ),
      ),
      Surface(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            ListTile(
              leading: const Icon(Icons.receipt_long_outlined),
              title: const Text('Lịch sử & thanh toán'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => openScreen(context, HistoryScreen(data: data)),
            ),
            if (auth.staff)
              ListTile(
                leading: const Icon(Icons.warning_amber_outlined),
                title: const Text('Cảnh báo & sự cố'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => openScreen(context, AlertsScreen(data: data)),
              ),
            ListTile(
              leading: const Icon(Icons.dns_outlined),
              title: const Text('Kết nối máy chủ'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => openScreen(context, ServerScreen(auth: auth)),
            ),
          ],
        ),
      ),
      OutlinedButton.icon(
        onPressed: () => auth.logout(),
        icon: const Icon(Icons.logout),
        label: const Text('Đăng xuất'),
      ),
      const SizedBox(height: 16),
      const Text(
        'Parkly Android · 1.0.0',
        style: TextStyle(color: Color(0xFF91A18B), fontSize: 12),
      ),
    ],
  );
}

class ProfileForm extends StatefulWidget {
  final AuthState auth;
  const ProfileForm({super.key, required this.auth});
  @override
  State<ProfileForm> createState() => _ProfileFormState();
}

class _ProfileFormState extends State<ProfileForm> {
  final form = GlobalKey<FormState>();
  late final TextEditingController name, hometown;
  DateTime? birthday;
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    name = TextEditingController(text: widget.auth.user!['full_name']);
    hometown = TextEditingController(text: widget.auth.user!['hometown']);
    birthday = DateTime.tryParse(widget.auth.user!['date_of_birth'] ?? '');
  }

  @override
  void dispose() {
    name.dispose();
    hometown.dispose();
    super.dispose();
  }

  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.auth.saveProfile({
        'full_name': name.text.trim(),
        'hometown': hometown.text.trim(),
        'date_of_birth': DateFormat('yyyy-MM-dd').format(birthday!),
      });
      if (mounted) {
        toast(context, 'Đã lưu thông tin.');
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Thông tin cá nhân')),
    body: Form(
      key: form,
      child: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          LabeledInput('Họ và tên', name, maxLength: 100),
          DateOfBirthField(
            value: birthday,
            onChanged: (v) => setState(() => birthday = v),
          ),
          LabeledInput('Quê quán', hometown, maxLength: 200),
          if (error != null) ErrorNotice(error!),
          PrimaryButton('Lưu thông tin', busy: busy, onPressed: save),
        ],
      ),
    ),
  );
}
