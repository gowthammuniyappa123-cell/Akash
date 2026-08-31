import pymysql


def get_connection():
    return pymysql.connect(
        host="localhost",
        port=3306,
        user="root",
        password="root",
        database="leaks_release",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )