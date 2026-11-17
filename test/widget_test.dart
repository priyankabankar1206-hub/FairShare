import 'package:flutter_test/flutter_test.dart';
import 'package:fairshare/main.dart';

void main() {
  testWidgets('FairShare app loads', (WidgetTester tester) async {
    await tester.pumpWidget(const FairShareApp());

    expect(find.text('FairShare'), findsOneWidget);
    expect(find.text('Welcome to FairShare'), findsOneWidget);
  });
}