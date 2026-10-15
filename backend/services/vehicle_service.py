from sqlalchemy import func

def normalized_plate(text):
    return text.upper().replace('-', '').replace('.', '').replace(' ', '')

def plate_expression(column):
    return func.upper(func.replace(func.replace(func.replace(column, '-', ''), '.', ''), ' ', ''))
