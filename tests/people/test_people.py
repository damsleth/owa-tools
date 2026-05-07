"""Pure-function tests for normalize_person."""
from owa_people.people import normalize_person


def test_normalize_people_shape():
    upstream = {
        'id': 'abc',
        'displayName': 'Ada Lovelace',
        'scoredEmailAddresses': [{'address': 'ada@example.com', 'relevanceScore': 0.9}],
        'jobTitle': 'Saksbehandler',
        'companyName': 'ACME',
    }
    out = normalize_person(upstream, 'people')
    assert out['id'] == 'abc'
    assert out['email'] == 'ada@example.com'
    assert out['source'] == 'people'
    assert out['businessPhones'] == []


def test_normalize_users_shape():
    upstream = {
        'id': 'oid-1',
        'displayName': 'Ole Kristian',
        'mail': 'ole@example.com',
        'userPrincipalName': 'ok@example.com',
        'jobTitle': 'Architect',
        'department': 'IT',
        'businessPhones': ['+47 1234'],
    }
    out = normalize_person(upstream, 'directory')
    # mail wins over userPrincipalName
    assert out['email'] == 'ole@example.com'
    assert out['businessPhones'] == ['+47 1234']
    assert out['source'] == 'directory'


def test_normalize_contacts_shape():
    upstream = {
        'id': 'c1',
        'displayName': 'Kjell',
        'emailAddresses': [{'name': 'Kjell', 'address': 'kjell@x.no'}],
    }
    out = normalize_person(upstream, 'contacts')
    assert out['email'] == 'kjell@x.no'
    assert out['source'] == 'contacts'


def test_normalize_handles_missing_fields():
    out = normalize_person({}, 'directory')
    assert out['id'] == ''
    assert out['email'] == ''
    assert out['businessPhones'] == []
    assert out['source'] == 'directory'
