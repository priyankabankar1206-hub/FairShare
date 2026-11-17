import 'dart:convert';
class MockApiClient {
  Future<List<Map<String, dynamic>>> getTeams() async {
    await Future.delayed(const Duration(milliseconds: 300));

    const response = '''
    [
      {
        "id": 1,
        "name": "FairShare Development Team",
        "members": 4,
        "status": "Active"
      }
    ]
    ''';

    final List<dynamic> data = jsonDecode(response);

    return data.cast<Map<String, dynamic>>();
  }

  Future<List<Map<String, dynamic>>> getMembers() async {
    await Future.delayed(const Duration(milliseconds: 300));

    const response = '''
    [
      {"name": "Joshika", "role": "AI/ML"},
      {"name": "Priyanka", "role": "Database"},
      {"name": "Shweta", "role": "Backend"},
      {"name": "Gauri", "role": "Frontend"}
    ]
    ''';

    final List<dynamic> data = jsonDecode(response);

    return data.cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> getTeamOverview() async {
    await Future.delayed(const Duration(milliseconds: 300));

    const response = '''
    {
      "teamScore": 85,
      "memberShares": {
        "Joshika": 28.0,
        "Priyanka": 25.0,
        "Shweta": 24.0,
        "Gauri": 23.0
      },
      "weeklyActivity": [20.0, 30.0, 25.0, 25.0, 28.0, 32.0, 35.0],
      "facets": {
        "Coding": [35.0, 20.0, 15.0, 30.0],
        "Reviews": [20.0, 35.0, 25.0, 20.0],
        "Planning": [25.0, 20.0, 35.0, 20.0]
      }
    }
    ''';

    return jsonDecode(response) as Map<String, dynamic>;
  }
}
