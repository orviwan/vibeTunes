from podplex.core.naming import album_directory, sanitize_component, track_filename


def test_sanitize_component_replaces_forbidden_chars():
    assert sanitize_component('AC/DC: Best?') == 'AC_DC_ Best_'


def test_sanitize_component_all_forbidden_chars_becomes_underscores():
    assert sanitize_component('???') == '___'


def test_sanitize_component_strips_trailing_dots_and_spaces():
    assert sanitize_component('Trailing... ') == 'Trailing'


def test_sanitize_component_truncates_long_names():
    long_name = "x" * 300
    result = sanitize_component(long_name)
    assert len(result.encode("utf-8")) <= 100


def test_sanitize_component_empty_after_strip_becomes_underscore():
    assert sanitize_component('   ') == '_'


def test_album_directory_rockbox_disc_with_year_and_disc():
    parts = album_directory("rockbox_disc", "The Band", "Great Album", "1999", 1)
    assert parts == ["The Band", "The Band-1999-Great Album", "CD 01"]


def test_album_directory_rockbox_disc_without_disc():
    parts = album_directory("rockbox_disc", "The Band", "Great Album", "1999", None)
    assert parts == ["The Band", "The Band-1999-Great Album"]


def test_album_directory_rockbox_disc_without_year():
    parts = album_directory("rockbox_disc", "The Band", "Great Album", None, None)
    assert parts == ["The Band", "The Band-Great Album"]


def test_album_directory_standard_ignores_year_and_disc():
    parts = album_directory("standard", "The Band", "Great Album", "1999", 2)
    assert parts == ["The Band", "Great Album"]


def test_track_filename_with_number():
    assert track_filename(3, "Song Title", ".flac") == "03 Song Title.flac"


def test_track_filename_without_number():
    assert track_filename(None, "Song Title", "mp3") == "Song Title.mp3"
