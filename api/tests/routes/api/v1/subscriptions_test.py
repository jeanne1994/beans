from yelp_beans.models import MeetingSubscription


def test_create_subscription_minimal(client, session):
    resp = client.post('v1/subscriptions/', json={'name': 'test', 'time_slots': [{'day': 'monday', 'hour': 9}]})
    row = session.query(MeetingSubscription).filter(MeetingSubscription.id == resp.json['id']).one()

    assert row.title == 'test'
    assert row.size == 2
    assert row.location == 'Online'
    assert row.office == 'Remote'
    assert row.rule_logic is None
    assert row.timezone == 'America/Los_Angeles'
    assert row.user_rules == []

    assert len(row.datetime) == 1
    assert row.datetime[0].datetime.weekday() == 0
    assert row.datetime[0].datetime.hour == 9
    assert row.datetime[0].datetime.minute == 0


def test_create_subscription_full(client, session):
    resp = client.post(
        'v1/subscriptions/',
        json={
            'location': 'test site',
            'name': 'test',
            'office': 'test office',
            'rule_logic': 'all',
            'rules': [{'field': 'email', 'value': 'tester@yelp.test'}],
            'time_slots': [{'day': 'monday', 'hour': 9, 'minute': 5}],
            'timezone': 'America/New_York'
        },
    )
    row = session.query(MeetingSubscription).filter(MeetingSubscription.id == resp.json['id']).one()

    assert row.title == 'test'
    assert row.size == 2
    assert row.location == 'test site'
    assert row.office == 'test office'
    assert row.rule_logic == 'all'
    assert row.timezone == 'America/New_York'

    assert len(row.datetime) == 1
    assert row.datetime[0].datetime.weekday() == 0
    assert row.datetime[0].datetime.hour == 9
    assert row.datetime[0].datetime.minute == 5

    assert len(row.user_rules) == 1
    assert row.user_rules[0].name == 'email'
    assert row.user_rules[0].value == 'tester@yelp.test'
