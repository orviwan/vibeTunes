from vibetunes.core.sync_engine import clean_fat32_name

def test_clean_fat32_name():
    assert clean_fat32_name('Song: Title? / Part * 1') == 'Song - Title Part 1'
    assert clean_fat32_name('What’s The Story? (Morning Glory)') == 'What’s The Story (Morning Glory)'
    assert clean_fat32_name('AC/DC: Back In Black') == 'ACDC - Back In Black'
