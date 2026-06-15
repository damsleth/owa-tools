from owa_core.profiles_args import normalize_all_flags, parse_profiles


def test_no_profiles_returns_empty_and_argv_intact():
    profiles, rest = parse_profiles(['messages', '--pretty'])
    assert profiles == []
    assert rest == ['messages', '--pretty']


def test_single_profile():
    profiles, rest = parse_profiles(['--profile', 'work', 'messages'])
    assert profiles == ['work']
    assert rest == ['messages']


def test_normalize_all_flags_rewrites_aliases():
    assert normalize_all_flags(['-A', 'messages']) == ['--profile', 'all', 'messages']
    assert normalize_all_flags(['--all-profiles', 'x']) == ['--profile', 'all', 'x']


def test_normalize_all_flags_leaves_other_argv_untouched():
    argv = ['--profile', 'work', 'messages', '--pretty']
    assert normalize_all_flags(argv) == argv


def test_normalize_all_flags_then_parse_yields_all_token():
    profiles, rest = parse_profiles(normalize_all_flags(['-A', 'messages']))
    assert profiles == ['all']
    assert rest == ['messages']


def test_many_profiles_preserve_order():
    profiles, rest = parse_profiles(
        ['--profile', 'a', '--profile', 'b', '--profile', 'c', 'events']
    )
    assert profiles == ['a', 'b', 'c']
    assert rest == ['events']


def test_duplicate_warns_once_and_is_dropped(capsys):
    profiles, rest = parse_profiles(
        ['--profile', 'a', '--profile', 'b', '--profile', 'a', 'messages']
    )
    assert profiles == ['a', 'b']
    assert rest == ['messages']
    err = capsys.readouterr().err
    assert err == 'warning: duplicate --profile a ignored\n'


def test_dedup_preserves_first_seen_order(capsys):
    profiles, _rest = parse_profiles(
        ['--profile', 'b', '--profile', 'a', '--profile', 'b']
    )
    assert profiles == ['b', 'a']
    assert 'duplicate --profile b ignored' in capsys.readouterr().err


def test_p_alias():
    profiles, rest = parse_profiles(['-p', 'work', '-p', 'home', 'list'])
    assert profiles == ['work', 'home']
    assert rest == ['list']


def test_mixed_long_and_short_flags():
    profiles, rest = parse_profiles(['--profile', 'a', '-p', 'b', 'messages'])
    assert profiles == ['a', 'b']
    assert rest == ['messages']


def test_interleaved_with_other_flags():
    profiles, rest = parse_profiles(
        ['messages', '--profile', 'a', '--unread', '--profile', 'b', '--top', '5']
    )
    assert profiles == ['a', 'b']
    assert rest == ['messages', '--unread', '--top', '5']


def test_dangling_trailing_profile_left_in_rest():
    profiles, rest = parse_profiles(['messages', '--profile'])
    assert profiles == []
    assert rest == ['messages', '--profile']


def test_dangling_trailing_p_alias_left_in_rest():
    profiles, rest = parse_profiles(['messages', '-p'])
    assert profiles == []
    assert rest == ['messages', '-p']


def test_dangling_does_not_raise_with_earlier_profile():
    profiles, rest = parse_profiles(['--profile', 'a', 'messages', '--profile'])
    assert profiles == ['a']
    assert rest == ['messages', '--profile']


def test_equals_form_supported():
    profiles, rest = parse_profiles(['--profile=work', '-p=home', 'messages'])
    assert profiles == ['work', 'home']
    assert rest == ['messages']


def test_empty_equals_form_left_untouched():
    profiles, rest = parse_profiles(['--profile=', 'messages'])
    assert profiles == []
    assert rest == ['--profile=', 'messages']
