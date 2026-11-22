import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:parkly_mobile/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Parkly logs in using the automatic development connection', (
    tester,
  ) async {
    const storage = FlutterSecureStorage();
    expect(await storage.read(key: 'parkly-server'), isNull);
    expect(await storage.read(key: 'parkly-token'), isNull);

    Future<void> waitFor(Finder target) async {
      final deadline = DateTime.now().add(const Duration(seconds: 15));
      while (target.evaluate().isEmpty && DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 200));
      }
      expect(target, findsWidgets);
    }

    await app.main();
    try {
      await waitFor(find.text('Chào bạn,'));
      await tester.enterText(
        find.byType(TextFormField).at(0),
        'direct-test@parkly.example',
      );
      await tester.enterText(
        find.byType(TextFormField).at(1),
        'ParklyTestRun26!',
      );
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.tap(find.widgetWithText(FilledButton, 'Đăng nhập'));
      await waitFor(find.text('Tổng quan'));
      await waitFor(find.text('Bãi Parkly kiểm thử trực tiếp'));
      await tester.tap(find.text('Bãi xe'));
      await waitFor(find.text('CG-001'));
      expect(await storage.read(key: 'parkly-token-server'), isNotNull);
      expect(await storage.read(key: 'parkly-server'), isNull);
    } finally {
      await tester.pumpWidget(const SizedBox.shrink());
      await storage.delete(key: 'parkly-token');
      await storage.delete(key: 'parkly-token-server');
    }
  });
}
