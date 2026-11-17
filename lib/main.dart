import 'package:flutter/material.dart';

import 'services/mock_api_client.dart';

void main() {
  runApp(const FairShareApp());
}

const purple = Color(0xFF5B5FEF);
const pageBg = Color(0xFFF8F8FC);

final MockApiClient mockApi = MockApiClient();

class FairShareApp extends StatelessWidget {
  const FairShareApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'FairShare',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: purple),
        useMaterial3: true,
        scaffoldBackgroundColor: pageBg,
      ),
      home: const SignInScreen(),
    );
  }
}

// COMMON APP BAR

PreferredSizeWidget fairShareAppBar(
  BuildContext context,
  String title, {
  bool isHome = false,
  bool showHome = true,
  bool showAlerts = true,
  bool showMenu = true,
}) {
  return PreferredSize(
    preferredSize: const Size.fromHeight(kToolbarHeight),
    child: Material(
      color: Colors.white,
      elevation: 1,
      child: SafeArea(
        bottom: false,
        child: SizedBox(
          height: kToolbarHeight,
          child: Row(
            children: [
              if (isHome)
                const SizedBox(width: 16)
              else
                IconButton(
                  tooltip: 'Back',
                  onPressed: () {
                    Navigator.of(context).maybePop();
                  },
                  icon: const Icon(Icons.arrow_back, color: Colors.black),
                ),

              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: Colors.black,
                  ),
                ),
              ),

              if (!isHome && showHome)
                IconButton(
                  tooltip: 'Home',
                  onPressed: () {
                    Navigator.of(context).pushAndRemoveUntil(
                      MaterialPageRoute(builder: (_) => const MyTeamsScreen()),
                      (route) => false,
                    );
                  },
                  icon: const Icon(
                    Icons.home_outlined,
                    color: Colors.black,
                    size: 25,
                  ),
                ),

              if (showAlerts)
                IconButton(
                  tooltip: 'Alerts',
                  onPressed: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const AlertsScreen()),
                    );
                  },
                  icon: const Icon(
                    Icons.notifications_outlined,
                    color: Colors.black,
                    size: 25,
                  ),
                ),

              if (showMenu)
                PopupMenuButton<String>(
                  tooltip: 'More screens',
                  icon: const Icon(
                    Icons.more_vert,
                    color: Colors.black,
                    size: 26,
                  ),
                  onSelected: (value) {
                    Widget screen;

                    switch (value) {
                      case 'instructor':
                        screen = const InstructorScreen();
                        break;
                      case 'survey':
                        screen = const PeerSurveyScreen();
                        break;
                      case 'model':
                        screen = const ModelCardScreen();
                        break;
                      case 'settings':
                        screen = const SettingsScreen();
                        break;
                      case 'gaming':
                        screen = const GamingDemoScreen();
                        break;
                      default:
                        screen = const ActivityLogScreen();
                    }

                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => screen),
                    );
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                      value: 'instructor',
                      child: Text('Instructor View'),
                    ),
                    PopupMenuItem(value: 'survey', child: Text('Peer Survey')),
                    PopupMenuItem(value: 'model', child: Text('Model Card')),
                    PopupMenuItem(
                      value: 'settings',
                      child: Text('Settings & Privacy'),
                    ),
                    PopupMenuItem(value: 'gaming', child: Text('Gaming Demo')),
                    PopupMenuItem(value: 'log', child: Text('Activity Log')),
                  ],
                ),

              const SizedBox(width: 8),
            ],
          ),
        ),
      ),
    ),
  );
}

// REUSABLE CARD
Widget fairCard({
  required String title,
  required Widget child,
  IconData? icon,
}) {
  return Card(
    color: Colors.white,
    elevation: 1,
    margin: const EdgeInsets.only(bottom: 16),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[
                Icon(icon, color: purple),
                const SizedBox(width: 8),
              ],
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    ),
  );
}

Widget pageContent(Widget child) {
  return Center(
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 850),
      child: child,
    ),
  );
}

// SIGN IN SCREEN
class SignInScreen extends StatelessWidget {
  const SignInScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: pageBg,
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Container(
            width: 420,
            padding: const EdgeInsets.all(30),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.groups_rounded, size: 65, color: purple),
                const SizedBox(height: 14),
                const Text(
                  'FairShare',
                  style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Team Contribution Analysis',
                  style: TextStyle(color: Colors.grey),
                ),
                const SizedBox(height: 28),
                const Text(
                  'Welcome to FairShare',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 10),
                const Text(
                  'Understand teamwork through transparent contribution insights.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 26),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.code),
                    label: const Text('Continue with GitHub'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF24292F),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.all(16),
                    ),
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const ConsentScreen(),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.g_mobiledata, size: 28),
                    label: const Text('Sign in with Google'),
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text(
                            'Google authentication will be connected later.',
                          ),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Authentication is currently a demonstration flow.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// CONSENT SCREEN
class ConsentScreen extends StatefulWidget {
  const ConsentScreen({super.key});

  @override
  State<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends State<ConsentScreen> {
  bool agreed = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Data & Privacy Consent'),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Container(
            width: 550,
            padding: const EdgeInsets.all(26),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.privacy_tip_outlined, size: 45, color: purple),
                const SizedBox(height: 16),
                const Text(
                  'Your Data, Your Control',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 14),
                const Text(
                  'FairShare analyses team contribution signals to understand how work is distributed.',
                ),
                const SizedBox(height: 18),
                const Text('What we analyse:'),
                const SizedBox(height: 8),
                const Text('• GitHub commits and activity'),
                const Text('• Code reviews and contributions'),
                const Text('• Team contribution patterns'),
                const SizedBox(height: 14),
                const Text(
                  'Contribution insights are decision-support information, not individual grades.',
                ),
                const SizedBox(height: 16),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: agreed,
                  onChanged: (value) {
                    setState(() => agreed = value ?? false);
                  },
                  title: const Text(
                    'I understand and agree to the data usage policy.',
                  ),
                  controlAffinity: ListTileControlAffinity.leading,
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: agreed
                        ? () {
                            Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(
                                builder: (_) => const MyTeamsScreen(),
                              ),
                            );
                          }
                        : null,
                    child: const Text('Agree and Continue'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// MY TEAM DASHBOARD
class MyTeamsScreen extends StatelessWidget {
  const MyTeamsScreen({super.key});

  IconData memberIcon(String role) {
    switch (role) {
      case 'AI/ML':
        return Icons.psychology;
      case 'Database':
        return Icons.storage;
      case 'Backend':
        return Icons.dns;
      default:
        return Icons.web;
    }
  }

  Widget memberTile(BuildContext context, String name, String role) {
    return Material(
      color: Colors.transparent,
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
        leading: CircleAvatar(
          backgroundColor: const Color(0xFFEDEEFF),
          child: Icon(memberIcon(role), color: purple),
        ),
        title: Text(name, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(role == 'AI/ML' ? 'AI / ML' : role),
        trailing: const Icon(Icons.arrow_forward_ios_rounded, size: 15),
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => MemberDetailScreen(name: name, role: role),
            ),
          );
        },
      ),
    );
  }

  Widget quickLink(
    BuildContext context,
    String title,
    String subtitle,
    IconData icon,
    Widget screen,
  ) {
    return Card(
      color: Colors.white,
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: const Color(0xFFEDEEFF),
          child: Icon(icon, color: purple),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.arrow_forward_ios, size: 15),
        onTap: () {
          Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'FairShare'),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: mockApi.getTeams(),
        builder: (context, teamSnapshot) {
          if (teamSnapshot.hasError ||
              !teamSnapshot.hasData ||
              teamSnapshot.data!.isEmpty) {
            return const Center(
              child: Text('Unable to load team information.'),
            );
          }

          final team = teamSnapshot.data!.first;

          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: pageContent(
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'My Team',
                    style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  const Text('Your project team and responsibilities'),
                  const SizedBox(height: 20),
                  fairCard(
                    title: team['name'].toString(),
                    icon: Icons.groups_rounded,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Team Contribution Analysis'),
                        const Divider(height: 28),
                        const Text(
                          'TEAM MEMBERS',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.grey,
                            letterSpacing: 1,
                            fontSize: 12,
                          ),
                        ),
                        FutureBuilder<List<Map<String, dynamic>>>(
                          future: mockApi.getMembers(),
                          builder: (context, snapshot) {
                            if (snapshot.connectionState ==
                                ConnectionState.waiting) {
                              return const Padding(
                                padding: EdgeInsets.all(20),
                                child: Center(
                                  child: CircularProgressIndicator(),
                                ),
                              );
                            }

                            if (snapshot.hasError || !snapshot.hasData) {
                              return const Text('Unable to load team members.');
                            }

                            if (snapshot.data!.isEmpty) {
                              return const Text('No team members found.');
                            }

                            return Column(
                              children: snapshot.data!.map((member) {
                                return memberTile(
                                  context,
                                  member['name'].toString(),
                                  member['role'].toString(),
                                );
                              }).toList(),
                            );
                          },
                        ),
                        const Divider(height: 28),
                        SizedBox(
                          width: double.infinity,
                          child: ElevatedButton.icon(
                            icon: const Icon(Icons.bar_chart),
                            label: const Text('View Team Overview'),
                            onPressed: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => const TeamOverviewScreen(),
                                ),
                              );
                            },
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'MORE FEATURES',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: Colors.grey,
                      letterSpacing: 1,
                    ),
                  ),
                  const SizedBox(height: 10),
                  quickLink(
                    context,
                    'Instructor Class View',
                    'Class progress, notes and disputes',
                    Icons.school_outlined,
                    const InstructorScreen(),
                  ),
                  quickLink(
                    context,
                    'Peer Survey',
                    'Submit contribution feedback',
                    Icons.poll_outlined,
                    const PeerSurveyScreen(),
                  ),
                  quickLink(
                    context,
                    'Model Card',
                    'Understand the analysis model',
                    Icons.info_outline,
                    const ModelCardScreen(),
                  ),
                  quickLink(
                    context,
                    'Settings & Privacy',
                    'Manage demonstration preferences',
                    Icons.settings_outlined,
                    const SettingsScreen(),
                  ),
                  quickLink(
                    context,
                    'Gaming Demo',
                    'View the demonstration activity',
                    Icons.extension_outlined,
                    const GamingDemoScreen(),
                  ),
                  quickLink(
                    context,
                    'Activity Log',
                    'View sample project activity',
                    Icons.history,
                    const ActivityLogScreen(),
                  ),
                  const SizedBox(height: 18),
                  const Text(
                    'Demo data is used throughout this application.',
                    style: TextStyle(color: Colors.grey, fontSize: 12),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

// MEMBER DETAIL SCREEN
class MemberDetailScreen extends StatelessWidget {
  final String name;
  final String role;

  const MemberDetailScreen({super.key, required this.name, required this.role});

  static const Map<String, List<Map<String, String>>> evidence = {
    'Joshika': [
      {
        'title': 'AI model development',
        'description': 'Sample activity: worked on the AI/ML module.',
        'type': 'Code contribution',
      },
      {
        'title': 'Model testing',
        'description': 'Sample activity: tested model outputs.',
        'type': 'Testing',
      },
      {
        'title': 'Technical discussion',
        'description': 'Sample activity: participated in discussions.',
        'type': 'Collaboration',
      },
    ],
    'Priyanka': [
      {
        'title': 'Database structure',
        'description': 'Sample activity: planned database tables.',
        'type': 'Database',
      },
      {
        'title': 'Data management',
        'description': 'Sample activity: worked on project records.',
        'type': 'Data contribution',
      },
      {
        'title': 'Database discussion',
        'description': 'Sample activity: discussed data requirements.',
        'type': 'Collaboration',
      },
    ],
    'Shweta': [
      {
        'title': 'API development',
        'description': 'Sample activity: worked on backend API structure.',
        'type': 'Backend',
      },
      {
        'title': 'Service integration',
        'description': 'Sample activity: planned service communication.',
        'type': 'Integration',
      },
      {
        'title': 'Backend testing',
        'description': 'Sample activity: tested sample API responses.',
        'type': 'Testing',
      },
    ],
    'Gauri': [
      {
        'title': 'Flutter UI development',
        'description': 'Sample activity: created FairShare frontend screens.',
        'type': 'Frontend',
      },
      {
        'title': 'Team Dashboard',
        'description': 'Sample activity: developed dashboard and charts.',
        'type': 'UI development',
      },
      {
        'title': 'Screen Navigation',
        'description': 'Sample activity: connected screen navigation.',
        'type': 'Frontend',
      },
    ],
  };

  List<String> reasons(double share) {
    return [
      'Contribution share in sample data: ${share.toStringAsFixed(0)}%.',
      'Assigned work area: $role.',
      'Evidence shown here consists of illustrative sample activities.',
    ];
  }

  void showEvidence(BuildContext context) {
    final records = evidence[name] ?? [];

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(22)),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(22),
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: Container(
                      width: 42,
                      height: 5,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade300,
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Text(
                    '$name - Evidence',
                    style: const TextStyle(
                      fontSize: 21,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  ...records.map(
                    (item) => ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const CircleAvatar(
                        backgroundColor: Color(0xFFEDEEFF),
                        child: Icon(Icons.description_outlined, color: purple),
                      ),
                      title: Text(item['title']!),
                      subtitle: Text('${item['description']}\n${item['type']}'),
                      isThreeLine: true,
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'These are mock records for demonstration. '
                    'They are not fetched from GitHub.',
                    style: TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Member Details'),
      body: FutureBuilder<Map<String, dynamic>>(
        future: mockApi.getTeamOverview(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError || !snapshot.hasData) {
            return const Center(
              child: Text(
                'Unable to load member information. Please try again.',
              ),
            );
          }

          final rawShares = snapshot.data!['memberShares'];

          if (rawShares is! Map ||
              rawShares.isEmpty ||
              !rawShares.containsKey(name)) {
            return const Center(
              child: Text(
                'No contribution information available for this member.',
              ),
            );
          }

          final shares = rawShares as Map<String, dynamic>;
          final share = (shares[name] as num?)?.toDouble() ?? 0;

          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: pageContent(
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: const TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(role),
                  const SizedBox(height: 20),
                  fairCard(
                    title: 'Contribution Share',
                    icon: Icons.bar_chart,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${share.toStringAsFixed(0)}%',
                          style: const TextStyle(
                            fontSize: 32,
                            fontWeight: FontWeight.bold,
                            color: purple,
                          ),
                        ),
                        const SizedBox(height: 12),
                        LinearProgressIndicator(
                          value: (share / 100).clamp(0.0, 1.0),
                          minHeight: 14,
                          color: purple,
                          backgroundColor: const Color(0xFFEDEEFF),
                        ),
                      ],
                    ),
                  ),
                  fairCard(
                    title: 'Why this score?',
                    icon: Icons.info_outline,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: reasons(share)
                          .map(
                            (reason) => Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Icon(
                                    Icons.check_circle_outline,
                                    color: purple,
                                    size: 20,
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(child: Text(reason)),
                                ],
                              ),
                            ),
                          )
                          .toList(),
                    ),
                  ),
                  fairCard(
                    title: 'Contribution Evidence',
                    icon: Icons.description_outlined,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${(evidence[name] ?? []).length} sample activity records available.',
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: () => showEvidence(context),
                            icon: const Icon(Icons.visibility_outlined),
                            label: const Text('View Evidence'),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Text(
                    'This is illustrative mock contribution data, not an actual GitHub measurement.',
                    style: TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

// TEAM OVERVIEW
class TeamOverviewScreen extends StatelessWidget {
  const TeamOverviewScreen({super.key});

  final List<String> names = const ['Joshika', 'Priyanka', 'Shweta', 'Gauri'];

  static const colors = [
    purple,
    Color(0xFF8588F5),
    Color(0xFFB2B4FA),
    Color(0xFFD6D7FF),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Team Overview'),
      body: FutureBuilder<Map<String, dynamic>>(
        future: mockApi.getTeamOverview(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError || !snapshot.hasData) {
            return const Center(
              child: Text('Unable to load team overview. Please try again.'),
            );
          }

          final data = snapshot.data!;
          final rawShares = data['memberShares'];
          final rawFacets = data['facets'];
          final rawActivity = data['weeklyActivity'];

          if (data.isEmpty ||
              rawShares is! Map ||
              rawShares.isEmpty ||
              rawFacets is! Map ||
              rawFacets.isEmpty ||
              rawActivity is! List ||
              rawActivity.isEmpty) {
            return const Center(
              child: Text('No team contribution data available yet.'),
            );
          }

          final shares = rawShares as Map<String, dynamic>;
          final facets = rawFacets as Map<String, dynamic>;
          final activity = rawActivity
              .map((e) => (e as num).toDouble())
              .toList();

          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: pageContent(
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Team Contribution Analysis',
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  const Text('Sample contribution data for your team'),
                  const SizedBox(height: 20),
                  fairCard(
                    title: 'Contribution Share',
                    icon: Icons.bar_chart,
                    child: Column(
                      children: names.map((name) {
                        final value = (shares[name] as num?)?.toDouble() ?? 0;

                        return Padding(
                          padding: const EdgeInsets.only(bottom: 16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(name),
                                  Text('${value.toInt()}%'),
                                ],
                              ),
                              const SizedBox(height: 7),
                              LinearProgressIndicator(
                                value: (value / 100).clamp(0.0, 1.0),
                                minHeight: 12,
                                color: purple,
                                backgroundColor: const Color(0xFFEDEEFF),
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                  fairCard(
                    title: 'Facet Comparison',
                    icon: Icons.compare_arrows,
                    child: Column(
                      children: facets.entries.map((facet) {
                        final values = (facet.value as List)
                            .map((v) => (v as num).toDouble())
                            .toList();

                        return Padding(
                          padding: const EdgeInsets.only(bottom: 18),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                facet.key,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Row(
                                children: List.generate(values.length, (i) {
                                  return Expanded(
                                    flex: values[i].toInt().clamp(1, 100),
                                    child: Container(
                                      height: 15,
                                      margin: const EdgeInsets.only(right: 3),
                                      decoration: BoxDecoration(
                                        color: colors[i % colors.length],
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                    ),
                                  );
                                }),
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                  fairCard(
                    title: 'Weekly Contribution Timeline',
                    icon: Icons.timeline,
                    child: Column(
                      children: List.generate(activity.length, (index) {
                        final value = activity[index];

                        return Padding(
                          padding: const EdgeInsets.only(bottom: 15),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Day ${index + 1}'),
                              const SizedBox(height: 7),
                              LinearProgressIndicator(
                                value: (value / 100).clamp(0.0, 1.0),
                                minHeight: 16,
                                color: purple,
                                backgroundColor: const Color(0xFFEDEEFF),
                              ),
                            ],
                          ),
                        );
                      }),
                    ),
                  ),
                  const Text(
                    'These are illustrative mock values, not actual GitHub measurements.',
                    style: TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

// ALERTS SCREEN
class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  final List<Map<String, dynamic>> alerts = [
    {
      'title': 'Contribution Analysis Updated',
      'message': 'Your team contribution overview has been updated.',
      'time': 'Today',
      'icon': Icons.insights,
      'read': false,
    },
    {
      'title': 'New Team Activity',
      'message': 'New sample development activity was added to the team.',
      'time': 'Today',
      'icon': Icons.groups_outlined,
      'read': false,
    },
    {
      'title': 'GitHub Connection Pending',
      'message': 'Connect GitHub to receive real contribution updates.',
      'time': 'Yesterday',
      'icon': Icons.code,
      'read': true,
    },
    {
      'title': 'Team Overview Available',
      'message': 'Your team contribution charts are ready to view.',
      'time': 'Yesterday',
      'icon': Icons.bar_chart,
      'read': true,
    },
  ];

  @override
  Widget build(BuildContext context) {
    final unread = alerts.where((a) => a['read'] == false).length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Alerts'),
        backgroundColor: Colors.white,
        actions: [
          TextButton(
            onPressed: unread == 0
                ? null
                : () {
                    setState(() {
                      for (final alert in alerts) {
                        alert['read'] = true;
                      }
                    });
                  },
            child: const Text('Mark all as read'),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 750),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              const Text(
                'Notifications',
                style: TextStyle(fontSize: 25, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              Text('$unread unread notifications'),
              const SizedBox(height: 20),
              if (alerts.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(
                    child: Text(
                      'No notifications available.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  ),
                )
              else
                ...alerts.map((alert) {
                  final read = alert['read'] as bool;

                  return Card(
                    color: read ? Colors.white : const Color(0xFFEDEEFF),
                    child: ListTile(
                      contentPadding: const EdgeInsets.all(12),
                      leading: CircleAvatar(
                        backgroundColor: Colors.white,
                        child: Icon(alert['icon'] as IconData, color: purple),
                      ),
                      title: Text(
                        alert['title'] as String,
                        style: TextStyle(
                          fontWeight: read
                              ? FontWeight.normal
                              : FontWeight.bold,
                        ),
                      ),
                      subtitle: Text('${alert['message']}\n${alert['time']}'),
                      isThreeLine: true,
                      trailing: read
                          ? const Icon(Icons.check_circle_outline)
                          : const Icon(Icons.circle, color: purple, size: 11),
                      onTap: () {
                        setState(() => alert['read'] = true);
                      },
                    ),
                  );
                }),
              const SizedBox(height: 12),
              const Text(
                'These are sample notifications. Real-time alerts will be connected later.',
                style: TextStyle(color: Colors.grey, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// POINT 8: INSTRUCTOR CLASS VIEW, NOTES AND DISPUTES
class InstructorScreen extends StatefulWidget {
  const InstructorScreen({super.key});

  @override
  State<InstructorScreen> createState() => _InstructorScreenState();
}

class _InstructorScreenState extends State<InstructorScreen> {
  final TextEditingController noteController = TextEditingController();
  final TextEditingController disputeController = TextEditingController();

  final List<String> notes = [
    'Review contribution distribution during the next class.',
    'Discuss project progress with all team members.',
  ];

  final List<String> disputes = [];

  @override
  void dispose() {
    noteController.dispose();
    disputeController.dispose();
    super.dispose();
  }

  void addNote() {
    final value = noteController.text.trim();
    if (value.isEmpty) return;

    setState(() {
      notes.add(value);
      noteController.clear();
    });
  }

  void addDispute() {
    final value = disputeController.text.trim();
    if (value.isEmpty) return;

    setState(() {
      disputes.add(value);
      disputeController.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Instructor Class View'),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: pageContent(
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Class Dashboard',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text('Review team progress and instructor feedback.'),
              const SizedBox(height: 20),
              fairCard(
                title: 'Class Summary',
                icon: Icons.school_outlined,
                child: const Column(
                  children: [
                    ListTile(
                      leading: Icon(Icons.groups, color: purple),
                      title: Text('FairShare Project Team'),
                      subtitle: Text('4 team members'),
                    ),
                    ListTile(
                      leading: Icon(Icons.assignment_outlined, color: purple),
                      title: Text('Project Status'),
                      subtitle: Text('Frontend demonstration in progress'),
                    ),
                  ],
                ),
              ),
              fairCard(
                title: 'Instructor Notes',
                icon: Icons.edit_note,
                child: Column(
                  children: [
                    TextField(
                      controller: noteController,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        hintText: 'Write an instructor note...',
                      ),
                    ),
                    const SizedBox(height: 10),
                    Align(
                      alignment: Alignment.centerRight,
                      child: ElevatedButton.icon(
                        onPressed: addNote,
                        icon: const Icon(Icons.add),
                        label: const Text('Add Note'),
                      ),
                    ),
                    const Divider(),
                    if (notes.isEmpty)
                      const Text(
                        'No instructor notes available.',
                        style: TextStyle(color: Colors.grey),
                      )
                    else
                      ...notes.map(
                        (note) => ListTile(
                          leading: const Icon(
                            Icons.sticky_note_2_outlined,
                            color: purple,
                          ),
                          title: Text(note),
                        ),
                      ),
                  ],
                ),
              ),
              fairCard(
                title: 'Disputes',
                icon: Icons.report_problem_outlined,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Submit a contribution-related concern for review.',
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: disputeController,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        hintText: 'Describe the concern...',
                      ),
                    ),
                    const SizedBox(height: 10),
                    Align(
                      alignment: Alignment.centerRight,
                      child: ElevatedButton.icon(
                        onPressed: addDispute,
                        icon: const Icon(Icons.send),
                        label: const Text('Submit Concern'),
                      ),
                    ),
                    const Divider(),
                    if (disputes.isEmpty)
                      const Text(
                        'No submitted concerns in this demonstration.',
                        style: TextStyle(color: Colors.grey),
                      ),
                    ...disputes.map(
                      (item) => ListTile(
                        leading: const Icon(
                          Icons.pending_actions,
                          color: purple,
                        ),
                        title: Text(item),
                        subtitle: const Text('Demo status: Submitted'),
                      ),
                    ),
                  ],
                ),
              ),
              const Text(
                'Instructor notes and disputes are stored locally for this demo only.',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// POINT 9: PEER SURVEY
class PeerSurveyScreen extends StatefulWidget {
  const PeerSurveyScreen({super.key});

  @override
  State<PeerSurveyScreen> createState() => _PeerSurveyScreenState();
}

class _PeerSurveyScreenState extends State<PeerSurveyScreen> {
  final List<String> names = ['Joshika', 'Priyanka', 'Shweta', 'Gauri'];
  late List<int> values;
  bool submitted = false;

  @override
  void initState() {
    super.initState();
    values = [25, 25, 25, 25];
  }

  int get total => values.fold(0, (sum, value) => sum + value);

  void updateValue(int index, int newValue) {
    setState(() {
      final others = List<int>.generate(
        4,
        (i) => i,
      ).where((i) => i != index).toList();

      final oldOtherTotal = 100 - values[index];
      final oldShares = others.map((i) => values[i]).toList();
      final remaining = 100 - newValue;

      values[index] = newValue;

      if (oldOtherTotal == 0) {
        final base = remaining ~/ others.length;
        final extra = remaining % others.length;

        for (var j = 0; j < others.length; j++) {
          values[others[j]] = base + (j < extra ? 1 : 0);
        }
      } else {
        var assigned = 0;

        for (var j = 0; j < others.length; j++) {
          final share = j == others.length - 1
              ? remaining - assigned
              : (remaining * oldShares[j] / oldOtherTotal).floor();

          values[others[j]] = share;
          assigned += share;
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Peer Survey'),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: pageContent(
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Peer Contribution Survey',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text('Distribute 100 points across the team members.'),
              const SizedBox(height: 20),
              fairCard(
                title: 'Contribution Allocation',
                icon: Icons.poll_outlined,
                child: Column(
                  children: List.generate(names.length, (index) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 18),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                names[index],
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text('${values[index]} points'),
                            ],
                          ),
                          Slider(
                            value: values[index].toDouble(),
                            min: 0,
                            max: 100,
                            divisions: 100,
                            activeColor: purple,
                            onChanged: submitted
                                ? null
                                : (value) => updateValue(index, value.round()),
                          ),
                        ],
                      ),
                    );
                  }),
                ),
              ),
              fairCard(
                title: 'Total Allocation',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$total / 100',
                      style: const TextStyle(
                        fontSize: 25,
                        fontWeight: FontWeight.bold,
                        color: purple,
                      ),
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: total / 100,
                      color: purple,
                      backgroundColor: const Color(0xFFEDEEFF),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      total == 100
                          ? 'Your allocation is valid.'
                          : 'Allocation must equal 100 points.',
                      style: TextStyle(
                        color: total == 100 ? Colors.green : Colors.red,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: total == 100 && !submitted
                      ? () {
                          setState(() => submitted = true);
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text(
                                'Demo survey submitted successfully.',
                              ),
                            ),
                          );
                        }
                      : null,
                  child: Text(submitted ? 'Survey Submitted' : 'Submit Survey'),
                ),
              ),
              if (submitted)
                TextButton(
                  onPressed: () => setState(() => submitted = false),
                  child: const Text('Edit Demo Response'),
                ),
              const SizedBox(height: 10),
              const Text(
                'Survey responses are not sent to a server in this demo.',
                style: TextStyle(color: Colors.grey, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// POINT 10: MODEL CARD
class ModelCardScreen extends StatelessWidget {
  const ModelCardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Model Card'),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: pageContent(
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'FairShare Model Information',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'An overview of the intended use and limitations of the analysis.',
              ),
              const SizedBox(height: 20),
              fairCard(
                title: 'Model Overview',
                icon: Icons.psychology_outlined,
                child: const Text(
                  'FairShare is designed to help teams understand how project contributions are distributed using available activity signals.',
                ),
              ),
              fairCard(
                title: 'Intended Use',
                icon: Icons.check_circle_outline,
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('• Support team contribution discussions.'),
                    SizedBox(height: 8),
                    Text('• Highlight patterns in project activity.'),
                    SizedBox(height: 8),
                    Text('• Help teams identify areas for discussion.'),
                  ],
                ),
              ),
              fairCard(
                title: 'Limitations',
                icon: Icons.warning_amber_outlined,
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('• GitHub activity does not represent all work.'),
                    SizedBox(height: 8),
                    Text('• Offline work may not appear in activity data.'),
                    SizedBox(height: 8),
                    Text('• Automated scores can be incomplete or misleading.'),
                    SizedBox(height: 8),
                    Text('• Sample values are not actual model predictions.'),
                  ],
                ),
              ),
              fairCard(
                title: 'Fairness & Transparency',
                icon: Icons.balance,
                child: const Text(
                  'Contribution insights should be reviewed with context. '
                  'They should not be treated as final grades or used as the only basis for decisions.',
                ),
              ),
              fairCard(
                title: 'Current Demonstration Status',
                child: const Text(
                  'This frontend currently displays mock data. A real model and backend connection must be supplied and validated separately.',
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// POINT 10: SETTINGS AND PRIVACY
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool notificationsEnabled = true;
  bool showDemoData = true;
  bool privacyAcknowledged = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Settings & Privacy'),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          pageContent(
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Preferences',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 18),
                fairCard(
                  title: 'Notifications',
                  icon: Icons.notifications_outlined,
                  child: SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Enable notifications'),
                    subtitle: const Text('Show sample app notifications.'),
                    value: notificationsEnabled,
                    activeThumbColor: purple,
                    onChanged: (value) {
                      setState(() => notificationsEnabled = value);
                    },
                  ),
                ),
                fairCard(
                  title: 'Demonstration Data',
                  icon: Icons.dataset_outlined,
                  child: SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Show sample data'),
                    subtitle: const Text(
                      'Controls this demonstration preference only.',
                    ),
                    value: showDemoData,
                    activeThumbColor: purple,
                    onChanged: (value) {
                      setState(() => showDemoData = value);
                    },
                  ),
                ),
                fairCard(
                  title: 'Privacy',
                  icon: Icons.lock_outline,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Review how project activity data may be used. '
                        'Real account permissions and data controls require backend integration.',
                      ),
                      const SizedBox(height: 12),
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: privacyAcknowledged,
                        onChanged: (value) {
                          setState(() => privacyAcknowledged = value ?? false);
                        },
                        title: const Text(
                          'I have reviewed the privacy information.',
                        ),
                      ),
                    ],
                  ),
                ),
                fairCard(
                  title: 'Account',
                  icon: Icons.account_circle_outlined,
                  child: const ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text('GitHub Account'),
                    subtitle: Text('Not connected in this demonstration'),
                    leading: Icon(Icons.code),
                  ),
                ),
                const Text(
                  'These settings currently apply only while the app is running. Persistent settings and secure account management are pending integration.',
                  style: TextStyle(color: Colors.grey, fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// POINT 15: GAMING DEMO
class GamingDemoScreen extends StatefulWidget {
  const GamingDemoScreen({super.key});

  @override
  State<GamingDemoScreen> createState() => _GamingDemoScreenState();
}

class _GamingDemoScreenState extends State<GamingDemoScreen> {
  int completedTasks = 0;

  final List<String> tasks = [
    'Create a project screen',
    'Review a teammate contribution',
    'Complete a navigation flow',
    'Check the team dashboard',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Gaming Demo'),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: pageContent(
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Team Progress Challenge',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'A simple demonstration of task completion and team progress.',
              ),
              const SizedBox(height: 20),
              fairCard(
                title: 'Progress',
                icon: Icons.emoji_events_outlined,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$completedTasks / ${tasks.length} tasks completed',
                      style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: purple,
                      ),
                    ),
                    const SizedBox(height: 12),
                    LinearProgressIndicator(
                      value: completedTasks / tasks.length,
                      minHeight: 12,
                      color: purple,
                      backgroundColor: const Color(0xFFEDEEFF),
                    ),
                  ],
                ),
              ),
              fairCard(
                title: 'Challenge Tasks',
                child: Column(
                  children: List.generate(tasks.length, (index) {
                    return CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: index < completedTasks,
                      title: Text(tasks[index]),
                      activeColor: purple,
                      onChanged: (value) {
                        setState(() {
                          if (value == true && index == completedTasks) {
                            completedTasks++;
                          } else if (value == false &&
                              index == completedTasks - 1) {
                            completedTasks--;
                          }
                        });
                      },
                    );
                  }),
                ),
              ),
              if (completedTasks == tasks.length)
                const Text(
                  'Challenge completed! Great team progress.',
                  style: TextStyle(
                    color: Colors.green,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              const SizedBox(height: 12),
              const Text(
                'This is a frontend gamification demonstration. It does not award real points.',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// POINT 15: NON-CODE ACTIVITY LOG
class ActivityLogScreen extends StatelessWidget {
  const ActivityLogScreen({super.key});

  final List<Map<String, String>> logs = const [
    {
      'title': 'Flutter project setup',
      'person': 'Gauri',
      'detail': 'Frontend project environment configured.',
      'date': 'Sample entry',
    },
    {
      'title': 'Team dashboard',
      'person': 'Gauri',
      'detail': 'Team dashboard and overview screens developed.',
      'date': 'Sample entry',
    },
    {
      'title': 'Contribution analysis',
      'person': 'Team',
      'detail': 'Sample contribution charts prepared.',
      'date': 'Sample entry',
    },
    {
      'title': 'Backend planning',
      'person': 'Shweta',
      'detail': 'Backend integration planning.',
      'date': 'Sample entry',
    },
    {
      'title': 'Database planning',
      'person': 'Priyanka',
      'detail': 'Database structure planning.',
      'date': 'Sample entry',
    },
    {
      'title': 'AI/ML module planning',
      'person': 'Joshika',
      'detail': 'AI/ML module planning.',
      'date': 'Sample entry',
    },
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: fairShareAppBar(context, 'Activity Log'),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          pageContent(
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Project Activity Log',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                const Text('A readable record of sample project activities.'),
                const SizedBox(height: 20),

                if (logs.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(
                      child: Text(
                        'No project activities recorded yet.',
                        style: TextStyle(color: Colors.grey),
                      ),
                    ),
                  )
                else
                  ...logs.map(
                    (entry) => Card(
                      color: Colors.white,
                      child: ListTile(
                        leading: const CircleAvatar(
                          backgroundColor: Color(0xFFEDEEFF),
                          child: Icon(Icons.history, color: purple),
                        ),
                        title: Text(
                          entry['title']!,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        subtitle: Text(
                          '${entry['person']} • ${entry['detail']}\n${entry['date']}',
                        ),
                        isThreeLine: true,
                      ),
                    ),
                  ),

                const SizedBox(height: 12),
                const Text(
                  'These are illustrative entries, not automatically collected activity records.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
