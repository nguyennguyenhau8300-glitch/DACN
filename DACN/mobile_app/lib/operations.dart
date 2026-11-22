import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'api.dart';
import 'common.dart';

class HistoryScreen extends StatefulWidget {
  final ParkingData data;
  const HistoryScreen({super.key, required this.data});
  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  bool payments = false, loading = true;
  int page = 0;
  int? busy;
  String? error;
  List<Json> rows = [];
  int generation = 0;
  @override
  void initState() {
    super.initState();
    unawaited(load());
  }

  Future<void> load() async {
    final current = ++generation;
    setState(() => loading = true);
    try {
      final list = await widget.data.api.list(
        '${payments ? '/payments' : '/parking-sessions'}?${widget.data.lotId == null ? '' : 'parking_lot_id=${widget.data.lotId}&'}limit=25&offset=${page * 25}',
      );
      if (mounted && current == generation) {
        setState(() {
          rows = list;
          error = null;
        });
      }
    } catch (e) {
      if (mounted && current == generation) {
        setState(() => error = e.toString());
      }
    } finally {
      if (mounted && current == generation) setState(() => loading = false);
    }
  }

  Future<void> checkout(Json row) async {
    if (!await confirm(
      context,
      'Xác nhận xe ra?',
      'Hệ thống kết thúc lượt gửi và tính phí theo giờ thực tế.',
    )) {
      return;
    }
    setState(() {
      busy = row['id'];
      error = null;
    });
    try {
      await widget.data.api.object(
        '/parking-sessions/${row['id']}/check-out',
        method: 'POST',
        body: {},
      );
      await widget.data.load(force: true);
      await load();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = null);
    }
  }

  Future<void> pay(Json row) async {
    setState(() {
      busy = row['id'];
      error = null;
    });
    try {
      final existing = await widget.data.api.list(
        '/payments?parking_session_id=${row['id']}&limit=1',
      );
      if (existing.isNotEmpty) {
        throw const ApiError('Lượt gửi này đã thanh toán.');
      }
      if (!mounted) return;
      if (!await confirm(
        context,
        'Đã nhận tiền mặt?',
        'Số tiền: ${money(row['total_amount'])}. Chỉ xác nhận sau khi đã nhận tiền.',
      )) {
        return;
      }
      await widget.data.api.object(
        '/payments',
        method: 'POST',
        body: {'parking_session_id': row['id'], 'payment_method': 'CASH'},
      );
      if (mounted) toast(context, 'Đã ghi nhận thanh toán tiền mặt.');
      await load();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = null);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Lịch sử & thanh toán'),
      actions: [
        IconButton(
          tooltip: 'Làm mới',
          onPressed: loading ? null : load,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: RefreshIndicator(
      onRefresh: load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(18),
        children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Lượt gửi')),
              ButtonSegment(value: true, label: Text('Thanh toán')),
            ],
            selected: {payments},
            onSelectionChanged: (v) {
              setState(() {
                payments = v.first;
                page = 0;
                rows = [];
              });
              unawaited(load());
            },
          ),
          const SizedBox(height: 20),
          if (error != null) ErrorNotice(error!),
          if (loading) const LinearProgressIndicator(),
          if (!loading && rows.isEmpty)
            const EmptyMessage('Chưa có lịch sử trong mục này.'),
          for (final r in rows)
            Surface(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: payments
                    ? [
                        Text(
                          'Biên nhận #${r['id']}',
                          style: const TextStyle(
                            fontSize: 19,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 10),
                        StatusChip(r['status']),
                        const SizedBox(height: 14),
                        Text(
                          money(r['amount']),
                          style: const TextStyle(
                            fontSize: 27,
                            fontWeight: FontWeight.w800,
                            color: forest,
                          ),
                        ),
                        Text('Lượt gửi #${r['parking_session_id']} · ${(r['transaction_code'] as String? ?? '').startsWith('SANDBOX-') ? 'Thử nghiệm, không chuyển tiền' : r['payment_method'] == 'CASH' ? 'Tiền mặt' : r['payment_method']}'),
                        Text(dateText(r['paid_at'])),
                      ]
                    : [
                        Text(
                          widget.data.vehicle(
                                r['vehicle_id'],
                              )?['license_plate'] ??
                              'Xe #${r['vehicle_id']}',
                          style: const TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 10),
                        StatusChip(r['status']),
                        const SizedBox(height: 12),
                        Text(
                          'Lượt #${r['id']} · Ô ${widget.data.spot(r['parking_spot_id'])?['spot_code'] ?? r['parking_spot_id'] ?? '—'}',
                        ),
                        Text('Vào: ${dateText(r['entry_time'])}'),
                        Text('Ra: ${dateText(r['exit_time'])}'),
                        const SizedBox(height: 10),
                        Text(
                          'Phí: ${money(r['total_amount'])}',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        if (widget.data.auth.staff &&
                            r['status'] == 'ACTIVE') ...[
                          const SizedBox(height: 14),
                          PrimaryButton(
                            'Xác nhận xe ra',
                            busy: busy == r['id'],
                            onPressed: busy == null ? () => checkout(r) : null,
                          ),
                          TextButton.icon(
                            onPressed: busy == null
                                ? () => Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) => AiScreen(
                                        data: widget.data,
                                        session: r,
                                      ),
                                    ),
                                  ).then((_) => load())
                                : null,
                            icon: const Icon(Icons.document_scanner_outlined),
                            label: const Text('Xe ra bằng ảnh AI'),
                          ),
                        ],
                        if (widget.data.auth.staff &&
                            r['status'] == 'COMPLETED') ...[
                          const SizedBox(height: 14),
                          OutlinedButton(
                            onPressed: busy == null ? () => pay(r) : null,
                            child: Text(
                              busy == r['id'] ? 'Đang xử lý…' : 'Thu tiền mặt',
                            ),
                          ),
                        ],
                      ],
              ),
            ),
          Row(
            children: [
              Expanded(child: Text('Trang ${page + 1}')),
              TextButton(
                onPressed: loading || page == 0
                    ? null
                    : () {
                        setState(() => page--);
                        unawaited(load());
                      },
                child: const Text('Trước'),
              ),
              TextButton(
                onPressed: loading || rows.length < 25
                    ? null
                    : () {
                        setState(() => page++);
                        unawaited(load());
                      },
                child: const Text('Sau'),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

class AlertsScreen extends StatefulWidget {
  final ParkingData data;
  const AlertsScreen({super.key, required this.data});
  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen>
    with WidgetsBindingObserver {
  static const kinds = {
    'ALL': 'Tất cả loại',
    'OVERHEAT': 'Quá nhiệt',
    'CHARGER_FAULT': 'Lỗi sạc',
    'CONNECTION_LOST': 'Mất kết nối / thiếu số đo',
    'WRONG_PARKING': 'Đỗ sai vị trí',
  };
  String status = 'OPEN', kind = 'ALL';
  int page = 0, generation = 0;
  Json? journal;
  bool loading = true, visible = true;
  int? busy;
  String? error;
  late Timer timer;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(load());
    timer = Timer.periodic(const Duration(seconds: 15), (_) {
      if (visible && !loading) unawaited(load());
    });
  }

  @override
  void dispose() {
    timer.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    visible = state == AppLifecycleState.resumed;
    if (visible) unawaited(load());
  }

  Future<void> load() async {
    final current = ++generation;
    setState(() => loading = true);
    try {
      final value = await widget.data.api.object(
        '/alerts?${widget.data.lotId == null ? '' : 'parking_lot_id=${widget.data.lotId}&'}status=$status&kind=$kind&limit=25&offset=${page * 25}',
      );
      if (mounted && current == generation) {
        setState(() {
          journal = value;
          error = null;
        });
      }
    } catch (e) {
      if (mounted && current == generation) {
        setState(() => error = e.toString());
      }
    } finally {
      if (mounted && current == generation) setState(() => loading = false);
    }
  }

  Future<void> ack(Json row) async {
    setState(() {
      busy = row['id'];
      error = null;
    });
    try {
      await widget.data.api.object(
        '/alerts/${row['id']}/acknowledge',
        method: 'PATCH',
      );
      await load();
      await widget.data.load(force: true);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = (journal?['items'] as List? ?? []).cast<Json>();
    return Scaffold(
      appBar: AppBar(title: const Text('Cảnh báo & sự cố')),
      body: RefreshIndicator(
        onRefresh: load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(18),
          children: [
            Surface(
              child: Row(
                children: [
                  const Icon(
                    Icons.warning_amber_rounded,
                    size: 35,
                    color: Color(0xFFB6782D),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Text(
                      '${journal?['open_count'] ?? 0} sự cố đang mở\n${journal?['unacknowledged_count'] ?? 0} chưa xác nhận',
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        height: 1.7,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            DropdownButtonFormField<String>(
              initialValue: status,
              decoration: const InputDecoration(labelText: 'Trạng thái sự cố'),
              items: const [
                DropdownMenuItem(value: 'OPEN', child: Text('Đang mở')),
                DropdownMenuItem(
                  value: 'ACKNOWLEDGED',
                  child: Text('Đã tiếp nhận'),
                ),
                DropdownMenuItem(value: 'RESOLVED', child: Text('Đã kết thúc')),
                DropdownMenuItem(value: 'ALL', child: Text('Tất cả lịch sử')),
              ],
              onChanged: (v) {
                setState(() {
                  status = v!;
                  page = 0;
                });
                unawaited(load());
              },
            ),
            const SizedBox(height: 14),
            DropdownButtonFormField<String>(
              initialValue: kind,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Loại sự cố'),
              items: kinds.entries
                  .map(
                    (e) => DropdownMenuItem(value: e.key, child: Text(e.value)),
                  )
                  .toList(),
              onChanged: (v) {
                setState(() {
                  kind = v!;
                  page = 0;
                });
                unawaited(load());
              },
            ),
            const SizedBox(height: 18),
            if (error != null) ErrorNotice(error!),
            if (loading) const LinearProgressIndicator(),
            if (!loading && rows.isEmpty)
              const EmptyMessage('Không có sự cố phù hợp bộ lọc.'),
            for (final r in rows)
              Surface(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      kinds[r['kind']] ?? r['kind'],
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                        color: r['severity'] == 'CRITICAL'
                            ? const Color(0xFFA73E30)
                            : forest,
                      ),
                    ),
                    const SizedBox(height: 10),
                    StatusChip(r['status']),
                    const SizedBox(height: 12),
                    Text(
                      'Ô ${r['spot_code']} · ${r['device_code']}',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 8),
                    Text(r['message']),
                    const SizedBox(height: 8),
                    if (r['kind'] == 'OVERHEAT')
                      Text(
                        'Nhiệt độ: ${r['details']['temperature_c']} °C · Ngưỡng mô phỏng ${r['details']['trigger_c']} °C',
                      ),
                    if (r['kind'] == 'WRONG_PARKING')
                      Text(
                        'Quan sát: ${vehicleName({'vehicle_type': r['details']['observed_vehicle_type'], 'energy_type': r['details']['observed_energy_type']})}\nÔ dành cho: ${vehicleName({'vehicle_type': r['details']['expected_vehicle_type'], 'energy_type': r['details']['expected_energy_type']})}',
                      ),
                    Text('Phát hiện: ${dateText(r['opened_at'])}'),
                    if (r['acknowledged_at'] != null)
                      Text('Tiếp nhận: ${dateText(r['acknowledged_at'])}'),
                    if (r['resolved_at'] != null) ...[
                      Text('Kết thúc: ${dateText(r['resolved_at'])}'),
                      Text(r['resolution'] ?? ''),
                    ],
                    if (r['status'] == 'OPEN') ...[
                      const SizedBox(height: 14),
                      PrimaryButton(
                        'Xác nhận tiếp nhận',
                        busy: busy == r['id'],
                        onPressed: busy == null ? () => ack(r) : null,
                      ),
                    ],
                  ],
                ),
              ),
            Row(
              children: [
                Expanded(child: Text('Trang ${page + 1}')),
                TextButton(
                  onPressed: loading || page == 0
                      ? null
                      : () {
                          setState(() => page--);
                          unawaited(load());
                        },
                  child: const Text('Trước'),
                ),
                TextButton(
                  onPressed:
                      loading || (page + 1) * 25 >= (journal?['total'] ?? 0)
                      ? null
                      : () {
                          setState(() => page++);
                          unawaited(load());
                        },
                  child: const Text('Sau'),
                ),
              ],
            ),
            const Text(
              'Xác nhận là đã tiếp nhận xử lý, không xóa lỗi. Cảnh báo dựa trên dữ liệu IoT/mô phỏng.',
              style: TextStyle(
                fontSize: 12,
                color: Color(0xFF7E8F7A),
                height: 1.7,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class AiScreen extends StatefulWidget {
  final ParkingData data;
  final Json? session;
  const AiScreen({super.key, required this.data, this.session});
  @override
  State<AiScreen> createState() => _AiScreenState();
}

class _AiScreenState extends State<AiScreen> {
  Uint8List? image;
  String filename = 'plate.jpg';
  Json? result;
  String? error;
  bool busy = false;
  int? spotId;
  Future<void> pick(ImageSource source) async {
    try {
      final file = await ImagePicker().pickImage(
        source: source,
        maxWidth: 1920,
        maxHeight: 1920,
        imageQuality: 90,
      );
      if (file == null) return;
      if (await file.length() > 8 * 1024 * 1024) {
        throw const ApiError('Ảnh tối đa 8 MB.');
      }
      final bytes = await file.readAsBytes();
      if (mounted) {
        setState(() {
          image = bytes;
          filename = file.name;
          result = null;
          spotId = null;
          error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = 'Không lấy được ảnh: $e');
    }
  }

  Future<void> recognize() async {
    if (image == null) return;
    setState(() {
      busy = true;
      error = null;
      result = null;
    });
    try {
      final value = await widget.data.api.photo(
        '/ai/recognize',
        image!,
        filename,
      );
      if (mounted) setState(() => result = value);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Json? get vehicle => result?['plate'] == null
      ? null
      : widget.data.vehicles
            .where(
              (v) => plateKey(v['license_plate']) == plateKey(result!['plate']),
            )
            .firstOrNull;
  bool get accepted =>
      result?['needs_review'] == false && result?['plate'] != null;
  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.data.api.photo(
        widget.session == null
            ? '/ai/check-in'
            : '/ai/check-out/${widget.session!['id']}',
        image!,
        filename,
        fields: widget.session == null ? {'parking_spot_id': '$spotId'} : {},
      );
      await widget.data.load(force: true);
      if (mounted) {
        toast(
          context,
          widget.session == null
              ? 'Đã nhận xe bằng ảnh.'
              : 'Đã trả xe bằng ảnh.',
        );
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final candidates = vehicle == null
        ? <Json>[]
        : widget.data.spots
              .where(
                (s) =>
                    s['available_for_booking'] == true &&
                    compatible(vehicle!, s),
              )
              .toList();
    final validSpotId = candidates.any((s) => s['id'] == spotId)
        ? spotId
        : null;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.session == null ? 'AI · Xe vào' : 'AI · Xe ra'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          const Text(
            'Đọc biển số từ ảnh',
            style: TextStyle(fontSize: 25, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 10),
          const Text(
            'Chụp rõ biển số. Xem kết quả trước khi xác nhận. Hệ thống chỉ nhận xe đã đăng ký.',
            style: TextStyle(height: 1.6, color: Color(0xFF7E8F7A)),
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 12,
            runSpacing: 10,
            children: [
              if (ImagePicker().supportsImageSource(ImageSource.camera))
                OutlinedButton.icon(
                  onPressed: busy ? null : () => pick(ImageSource.camera),
                  icon: const Icon(Icons.photo_camera_outlined),
                  label: const Text('Chụp ảnh'),
                ),
              OutlinedButton.icon(
                onPressed: busy ? null : () => pick(ImageSource.gallery),
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Chọn ảnh'),
              ),
            ],
          ),
          const SizedBox(height: 20),
          if (image != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: Image.memory(image!, height: 220, fit: BoxFit.contain),
            ),
            const SizedBox(height: 18),
            PrimaryButton(
              'Nhận diện biển số',
              busy: busy,
              onPressed: recognize,
            ),
          ],
          if (error != null) ...[
            const SizedBox(height: 16),
            ErrorNotice(error!),
          ],
          if (result != null) ...[
            const SizedBox(height: 18),
            Surface(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    result!['plate'] ?? 'Chưa đọc được biển số',
                    style: const TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      color: forest,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Điểm OCR: ${((num.tryParse('${result!['confidence']}') ?? 0) * 100).toStringAsFixed(1)}%',
                  ),
                  if (!accepted)
                    const Padding(
                      padding: EdgeInsets.only(top: 10),
                      child: Text(
                        'Cần kiểm tra lại ảnh. Chọn ảnh rõ hơn trước khi ghi nhận.',
                        style: TextStyle(color: Color(0xFFA55334)),
                      ),
                    ),
                  if (accepted && vehicle != null) Text(vehicleName(vehicle!)),
                  if (accepted && vehicle == null)
                    const Text(
                      'Biển số chưa nằm trong danh sách xe đã đăng ký.',
                    ),
                ],
              ),
            ),
            if (widget.session == null && accepted && vehicle != null) ...[
              DropdownButtonFormField<int>(
                key: ValueKey(validSpotId),
                initialValue: validSpotId,
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
                onChanged: busy ? null : (v) => setState(() => spotId = v),
              ),
              const SizedBox(height: 18),
            ],
            PrimaryButton(
              widget.session == null ? 'Xác nhận xe vào' : 'Xác nhận xe ra',
              busy: busy,
              onPressed:
                  accepted &&
                      (widget.session != null ||
                          (vehicle != null && validSpotId != null))
                  ? save
                  : null,
            ),
          ],
        ],
      ),
    );
  }
}
