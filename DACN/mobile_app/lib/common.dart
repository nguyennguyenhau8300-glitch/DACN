import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'api.dart';

const forest = Color(0xFF145C48);
const mint = Color(0xFFD2EAB9);
const canvas = Color(0xFFF4F7F3);
DateTime vietnamNow() => DateTime.now().toUtc().add(const Duration(hours: 7));
const bookingPolicyMinutes = 120;
DateTime bookingExpiry(DateTime start, [int minutes = bookingPolicyMinutes]) =>
    start.add(Duration(minutes: minutes));
String wallTime(DateTime value) =>
    DateFormat("yyyy-MM-dd'T'HH:mm:ss").format(value);
String dateText(dynamic value) {
  if (value == null || value.toString().isEmpty) return '—';
  final raw = value.toString();
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return '—';
  final hasZone = RegExp(r'[Zz]|[+-]\d\d:\d\d$').hasMatch(raw);
  return DateFormat('dd/MM/yyyy HH:mm')
      .format(hasZone ? parsed.toUtc().add(const Duration(hours: 7)) : parsed);
}

String birthText(dynamic value) => value == null
    ? 'Chưa bổ sung'
    : DateFormat('dd/MM/yyyy').format(DateTime.parse(value as String));
String money(dynamic value) => NumberFormat.currency(
  locale: 'vi_VN',
  symbol: 'đ',
  decimalDigits: 0,
).format(num.tryParse('$value') ?? 0);
String plateKey(String value) =>
    value.toUpperCase().replaceAll(RegExp(r'[ .-]'), '');
String plateExample(String type) =>
    type == 'CAR' ? 'VD: 30F-222.22' : 'VD: 29-B1 555.55';
String vehicleName(Json value) =>
    '${['CAR', 'DISABLED'].contains(value['vehicle_type'] ?? value['spot_type']) ? 'Ô tô' : 'Xe máy'} ${value['energy_type'] == 'ELECTRIC' ? 'điện' : 'xăng'}';
bool compatible(Json vehicle, Json spot) =>
    vehicle['vehicle_type'] ==
        (spot['spot_type'] == 'DISABLED' ? 'CAR' : spot['spot_type']) &&
    vehicle['energy_type'] == spot['energy_type'];
const statusNames = {
  'AVAILABLE': 'Còn trống',
  'OCCUPIED': 'Có xe',
  'RESERVED': 'Đã giữ chỗ',
  'MAINTENANCE': 'Bảo trì',
  'CONFIRMED': 'Đã xác nhận',
  'PENDING': 'Chờ xác nhận',
  'CANCELLED': 'Đã hủy',
  'EXPIRED': 'Hết hạn',
  'ACTIVE': 'Đang gửi',
  'COMPLETED': 'Hoàn tất',
  'SUCCESS': 'Đã thanh toán',
  'PLANNED': 'Chưa vận hành',
  'READY': 'Sẵn sàng',
  'OFFLINE': 'Mất kết nối',
  'FAULT': 'Báo lỗi',
  'CHARGING': 'Đang sạc',
  'OPEN': 'Chưa xác nhận',
  'ACKNOWLEDGED': 'Đã tiếp nhận',
  'RESOLVED': 'Đã kết thúc',
};
const bookingArrivalLabels = {
  'UPCOMING': 'Chưa tới giờ nhận xe',
  'READY': 'Có thể nhận xe',
  'CHECKED_IN': 'Đã nhận xe',
};
const roleNames = {
  'ADMIN': 'Quản trị viên',
  'MANAGER': 'Quản lý',
  'SECURITY': 'Bảo vệ',
  'CUSTOMER': 'Khách hàng',
};

class Brand extends StatelessWidget {
  final double size;
  const Brand({super.key, this.size = 48});
  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: mint,
          borderRadius: BorderRadius.circular(size / 3),
        ),
        alignment: Alignment.center,
        child: Text(
          'P',
          style: TextStyle(
            fontSize: size * .66,
            height: 1,
            color: forest,
            fontWeight: FontWeight.w900,
          ),
        ),
      ),
      const SizedBox(width: 10),
      const Text(
        'parkly',
        style: TextStyle(
          color: forest,
          fontSize: 26,
          fontWeight: FontWeight.w800,
          letterSpacing: -1,
        ),
      ),
    ],
  );
}

class StatusChip extends StatelessWidget {
  final String status;
  const StatusChip(this.status, {super.key});
  @override
  Widget build(BuildContext context) {
    final good = [
      'AVAILABLE',
      'READY',
      'COMPLETED',
      'SUCCESS',
      'RESOLVED',
    ].contains(status);
    final bad = ['FAULT', 'OFFLINE', 'CANCELLED'].contains(status);
    final color = good
        ? forest
        : bad
        ? const Color(0xFFAA4434)
        : const Color(0xFF926D25);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .09),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        statusNames[status] ?? status,
        style: TextStyle(
          fontSize: 12,
          color: color,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class Surface extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  const Surface({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
  });
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 14),
    child: Material(
      color: Colors.white,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: const BorderSide(color: Color(0xFFE2E9E0)),
      ),
      child: Padding(padding: padding, child: child),
    ),
  );
}

class ErrorNotice extends StatelessWidget {
  final String message;
  const ErrorNotice(this.message, {super.key});
  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF0EA),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(
        message,
        style: const TextStyle(color: Color(0xFF9C4835), height: 1.5),
      ),
    ),
  );
}

class PrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool busy;
  final IconData? icon;
  const PrimaryButton(
    this.label, {
    super.key,
    this.onPressed,
    this.busy = false,
    this.icon,
  });
  @override
  Widget build(BuildContext context) => SizedBox(
    width: double.infinity,
    child: FilledButton(
      onPressed: busy ? null : onPressed,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (busy)
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            else if (icon != null)
              Icon(icon, size: 20),
            if (busy || icon != null) const SizedBox(width: 10),
            Flexible(child: Text(label)),
          ],
        ),
      ),
    ),
  );
}

class EmptyMessage extends StatelessWidget {
  final String message;
  const EmptyMessage(this.message, {super.key});
  @override
  Widget build(BuildContext context) => Surface(
    child: SizedBox(
      width: double.infinity,
      child: Column(
        children: [
          const Icon(
            Icons.local_parking_rounded,
            size: 38,
            color: Color(0xFF93AA95),
          ),
          const SizedBox(height: 12),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Color(0xFF6F8472), height: 1.6),
          ),
        ],
      ),
    ),
  );
}

void toast(BuildContext context, String message) {
  if (context.mounted) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}

Future<bool> confirm(
  BuildContext context,
  String title,
  String message,
) async =>
    await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('Đóng'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('Xác nhận'),
          ),
        ],
      ),
    ) ??
    false;

class LabeledInput extends StatelessWidget {
  final String label;
  final TextEditingController controller;
  final bool required;
  final bool obscure;
  final String? hint;
  final TextInputType? keyboard;
  final int? maxLength;
  const LabeledInput(
    this.label,
    this.controller, {
    super.key,
    this.required = true,
    this.obscure = false,
    this.hint,
    this.keyboard,
    this.maxLength,
  });
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: TextFormField(
      controller: controller,
      obscureText: obscure,
      keyboardType: keyboard,
      maxLength: maxLength,
      enableSuggestions: !obscure,
      autocorrect: !obscure,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        counterText: '',
      ),
      validator: (v) => required && (v == null || v.trim().isEmpty)
          ? 'Vui lòng nhập $label'
          : null,
    ),
  );
}

class DateOfBirthField extends StatelessWidget {
  final DateTime? value;
  final ValueChanged<DateTime> onChanged;
  const DateOfBirthField({
    super.key,
    required this.value,
    required this.onChanged,
  });
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: FormField<DateTime>(
      key: ValueKey(value),
      initialValue: value,
      validator: (v) => v == null ? 'Chọn ngày tháng năm sinh' : null,
      builder: (field) => InkWell(
        onTap: () async {
          final now = vietnamNow();
          final date = await showDatePicker(
            context: context,
            initialDate: value ?? DateTime(now.year - 20),
            firstDate: DateTime(1900),
            lastDate: DateTime(now.year, now.month, now.day),
          );
          if (date != null) {
            field.didChange(date);
            onChanged(date);
          }
        },
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: 'Ngày tháng năm sinh',
            errorText: field.errorText,
            suffixIcon: const Icon(Icons.calendar_month_outlined),
          ),
          child: Text(
            value == null
                ? 'Chọn ngày sinh'
                : DateFormat('dd/MM/yyyy').format(value!),
          ),
        ),
      ),
    ),
  );
}
