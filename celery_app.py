from app.tasks.virus_scan import celery_app

if __name__ == '__main__':
    celery_app.start() 