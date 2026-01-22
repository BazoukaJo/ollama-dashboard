import logging

def test_fail_output():
    print('PRINT: This should be visible')
    logging.error('LOG: This should be visible')
    assert False, 'Intentional failure for output test'
