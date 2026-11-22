import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api.dart';
import 'common.dart';
import 'screens.dart' show BookingScreen;

class FindLotScreen extends StatefulWidget {
  final ParkingData data;
  const FindLotScreen({super.key, required this.data});
  @override
  State<FindLotScreen> createState() => _FindLotScreenState();
}
class _FindLotScreenState extends State<FindLotScreen> {
  String query = '';
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Tìm bãi xe')),
    body: ListView(padding: const EdgeInsets.all(20), children: [
      TextField(decoration: const InputDecoration(labelText: 'Tên hoặc địa chỉ bãi'), onChanged: (v) => setState(() => query = v.toLowerCase().trim())),
      const SizedBox(height: 18),
      for (final lot in widget.data.lots.where((l) => '${l['name']} ${l['address']}'.toLowerCase().contains(query)))
        Card(child: ListTile(title: Text(lot['name']), subtitle: Text(lot['address'] ?? ''), trailing: const Icon(Icons.chevron_right), onTap: () {
          widget.data.chooseLot(lot['id'] as int);
          Navigator.pop(context);
        })),
    ]),
  );
}

class RoutingScreen extends StatefulWidget {
  final ParkingData data;
  const RoutingScreen({super.key, required this.data});
  @override
  State<RoutingScreen> createState() => _RoutingScreenState();
}
class _RoutingScreenState extends State<RoutingScreen> {
  int? vehicle;
  Json? graph, result;
  bool busy = false;
  String? error;
  final double weight = 1;
  Future<void> suggest() async {
    final lot = widget.data.lotId;
    if (lot == null || vehicle == null) return;
    setState(() {busy = true; error = null;});
    try {
      final map = await widget.data.api.object('/parking-lots/$lot/map');
      final recommendation = await widget.data.api.object('/parking-lots/$lot/recommendation?vehicle_id=$vehicle&walk_weight=$weight');
      if (mounted) setState(() {graph = map; result = recommendation;});
    } catch (e) {if (mounted) setState(() => error = e.toString());}
    finally {if (mounted) setState(() => busy = false);}
  }
  @override
  Widget build(BuildContext context) {
    final candidates = (result?['candidates'] as List? ?? []).cast<Json>();
    return Scaffold(appBar: AppBar(title: const Text('Gợi ý ô & đường đi')), body: ListView(padding: const EdgeInsets.all(20), children: [
      const Text('Tính đường xe từ cổng vào và khoảng cách đi bộ đến lối đi / thang máy.'),
      const SizedBox(height: 16),
      DropdownButtonFormField<int>(initialValue: vehicle, isExpanded: true, decoration: const InputDecoration(labelText: 'Phương tiện'),
        items: widget.data.vehicles.map((v) => DropdownMenuItem(value: v['id'] as int, child: Text('${v['license_plate']} · ${vehicleName(v)}', overflow: TextOverflow.ellipsis))).toList(),
        onChanged: busy ? null : (id) => setState(() {vehicle = id; result = null;})),
      const SizedBox(height: 16),
      FilledButton(onPressed: busy || vehicle == null ? null : suggest, child: Text(busy ? 'Đang tìm…' : 'Tìm ô phù hợp')),
      if (error != null) Padding(padding: const EdgeInsets.all(12), child: Text(error!, style: const TextStyle(color: Colors.red))),
      if (result != null) ...[
        const SizedBox(height: 14), Text(result!['notice']),
        if (candidates.isEmpty) const Text('Không có ô phù hợp hoặc không có đường đi.'),
        for (final candidate in candidates) Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(candidate['spot_code'], style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          Text('Xe đi ${candidate['driving_distance']} · Đi bộ ${candidate['walking_distance']} ${result!['units']}'),
          TextButton(onPressed: () {
            final spot = widget.data.spot(candidate['spot_id'] as int);
            if (spot != null) Navigator.push(context, MaterialPageRoute(builder: (_) => BookingScreen(data: widget.data, initialSpot: spot, initialVehicleId: vehicle)));
          }, child: const Text('Đặt ô này')),
        ]))),
      ],
      if (graph != null) ...[
        const SizedBox(height: 16), Text(graph!['name']),
        const Text('Cam: đường xe · Xanh nét đứt: đi bộ. Có thể kéo và phóng to sơ đồ.'),
        const SizedBox(height: 10),
        SizedBox(height: 400, child: ClipRect(child: InteractiveViewer(constrained: false, minScale: .3, maxScale: 4,
          child: CustomPaint(size: const Size(600, 1600), painter: RoutePainter(graph!, candidates.firstOrNull, widget.data.spots))))),
      ],
    ]));
  }
}

class RoutePainter extends CustomPainter {
  final Json graph;
  final Json? route;
  final List<Json> spots;
  RoutePainter(this.graph, this.route, this.spots);
  @override
  void paint(Canvas canvas, Size size) {
    final rows = (graph['nodes'] as List).cast<Json>();
    final nodes = {for (final n in rows) n['id'] as String: n};
    final maxX = rows.map((n) => (n['x'] as num).toDouble()).reduce(math.max);
    final maxY = rows.map((n) => (n['y'] as num).toDouble()).reduce(math.max);
    final minX = rows.map((n) => (n['x'] as num).toDouble()).reduce(math.min);
    final minY = rows.map((n) => (n['y'] as num).toDouble()).reduce(math.min);
    final scale = math.min((size.width - 40) / (maxX - minX + 10), (size.height - 40) / (maxY - minY + 10));
    Offset point(Json n) => Offset(20 + ((n['x'] as num).toDouble() - minX) * scale, 20 + ((n['y'] as num).toDouble() - minY) * scale);
    for (final edge in (graph['edges'] as List).cast<Json>()) {
      canvas.drawLine(point(nodes[edge['source']]!), point(nodes[edge['target']]!), Paint()..color = edge['blocked'] == true ? Colors.red : Colors.grey.shade300..strokeWidth = 3);
    }
    for (final field in ['route', 'walking_route']) {
      final ids = (route?[field] as List? ?? []).cast<String>();
      for (int i = 1; i < ids.length; i++) {
        final a = point(nodes[ids[i-1]]!), b = point(nodes[ids[i]]!);
        final paint = Paint()..color = field == 'route' ? Colors.orange : Colors.blue..strokeWidth = 4;
        if (field == 'route') {canvas.drawLine(a, b, paint);} else {
          final distance = (b-a).distance;
          for (double step = 0; step < distance; step += 12) {
            canvas.drawLine(Offset.lerp(a,b,step/distance)!, Offset.lerp(a,b,math.min(1,(step+6)/distance))!, paint);
          }
        }
      }
    }
    for (final node in rows.where((n) => n['kind'] != 'LANE')) {
      final spot = spots.where((s) => s['id'] == node['spot_id']).firstOrNull;
      final color = spot == null ? const Color(0xFF155B49) : switch (spot['status']) {'AVAILABLE' => const Color(0xFFD8EDC4), 'RESERVED' => Colors.amber.shade200, 'OCCUPIED' => Colors.red.shade200, _ => Colors.grey.shade300};
      final p = point(node);
      canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center:p,width:5.5*scale,height:3.4*scale), const Radius.circular(4)), Paint()..color=color);
      final text = TextPainter(text:TextSpan(text:node['label'], style:TextStyle(fontSize:math.max(9,scale*1.1),color:spot==null?Colors.white:Colors.black)), textDirection:TextDirection.ltr)..layout(maxWidth:5.3*scale);
      text.paint(canvas,p-Offset(text.width/2,text.height/2));
    }
  }
  @override
  bool shouldRepaint(covariant RoutePainter oldDelegate) => true;
}

class CheckoutScreen extends StatefulWidget {
  final ParkingData data;
  const CheckoutScreen({super.key,required this.data});
  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}
class _CheckoutScreenState extends State<CheckoutScreen> {
  List<Json> sessions=[];
  Json? order;
  int? selected;
  int page=0;
  bool busy=false;
  String? error;
  @override
  void initState(){super.initState();load();}
  Future<void> load() async {
    try {
      final rows=await widget.data.api.list('/parking-sessions?parking_lot_id=${widget.data.lotId}&session_status=COMPLETED&limit=25&offset=${page*25}');
      if(mounted)setState((){sessions=rows;selected=null;order=null;});
    }catch(e){if(mounted)setState(()=>error=e.toString());}
  }
  Future<void> create() async {
    setState((){busy=true;error=null;});
    try {
      final value=await widget.data.api.object('/checkout/orders',method:'POST',body:{'parking_session_id':selected,'provider':'INTERNAL'});
      if(mounted)setState(()=>order=value);
    }catch(e){if(mounted)setState(()=>error=e.toString());}
    finally{if(mounted)setState(()=>busy=false);}
  }
  Future<void> check() async {
    final id=order?['id'];if(id==null)return;
    try{final value=await widget.data.api.object('/checkout/orders/$id');if(mounted&&order?['id']==id)setState(()=>order={...order!,...value});}
    catch(e){if(mounted)setState(()=>error=e.toString());}
  }
  @override
  Widget build(BuildContext context)=>Scaffold(appBar:AppBar(title:const Text('Thanh toán thử nghiệm')),body:ListView(padding:const EdgeInsets.all(20),children:[
    const Text('Mô phỏng nội bộ, không chuyển tiền. QR mở trang thử nghiệm, không phải mã ngân hàng.'),
    const SizedBox(height:16),
    DropdownButtonFormField<int>(key:ValueKey(page),initialValue:selected,isExpanded:true,decoration:const InputDecoration(labelText:'Lượt gửi đã trả xe'),
      items:sessions.map((s)=>DropdownMenuItem(value:s['id'] as int,child:Text('#${s['id']} · ${money(s['total_amount'])}'))).toList(),onChanged:busy?null:(id)=>setState((){selected=id;order=null;})),
    Row(children:[TextButton(onPressed:page==0?null:(){setState(()=>page--);load();},child:const Text('Trước')),Text('Trang ${page+1}'),TextButton(onPressed:sessions.length<25?null:(){setState(()=>page++);load();},child:const Text('Sau'))]),
    FilledButton(onPressed:selected==null||busy?null:create,child:Text(busy?'Đang tạo…':'Tạo thanh toán thử')),
    if(error!=null)Padding(padding:const EdgeInsets.all(12),child:Text(error!,style:const TextStyle(color:Colors.red))),
    if(order!=null)...[
      const SizedBox(height:20),Text(money(order!['amount']),style:const TextStyle(fontSize:28,fontWeight:FontWeight.bold)),Text('Lượt gửi #${order!['parking_session_id']} · Trạng thái: ${order!['status']}'),
      if(order!['qr_url']!=null)Image.network(order!['qr_url'],height:240,errorBuilder:(_,e,stack)=>const Text('Không tải được QR; dùng nút mở trang thử.')),
      FilledButton(onPressed:()async{try{if(!await launchUrl(Uri.parse(order!['checkout_url']),mode:LaunchMode.externalApplication))throw const ApiError('Không mở được trình duyệt');}catch(e){if(mounted)setState(()=>error=e.toString());}},child:const Text('Mở trang mô phỏng')),
      const Text('Sau khi mô phỏng, quay lại app và kiểm tra kết quả.'),
      OutlinedButton(onPressed:check,child:const Text('Kiểm tra kết quả')),
    ],
  ]));
}
