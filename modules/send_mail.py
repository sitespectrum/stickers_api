import datetime
import resend
import uuid
from api.models import ConfigObject
from rlsWebsite.settings import RESEND_TOKEN, EMAIL_SAFETY_LIMIT


def increment_and_check_limits(high_priority=False):
    # Retrieve the ConfigObject instance named 'email_management'
    try:
        email_management = ConfigObject.objects.get(name='email_management')
    except ConfigObject.DoesNotExist:
        print("ConfigObject with name 'email_management' does not exist.")
        return False

    if email_management.last_updated != datetime.datetime.now().date():
        email_management.data['sent_today'] = 0
    if email_management.last_updated.month != datetime.datetime.now().date().month:
        email_management.data['sent_this_month'] = 0

    email_management.data['sent_today'] += 1
    email_management.data['sent_this_month'] += 1
    email_management.last_updated = datetime.datetime.now().date()

    if email_management.data['sent_today'] > email_management.data['daily_limit'] - EMAIL_SAFETY_LIMIT and not \
            high_priority:
        return False

    if email_management.data['sent_today'] > email_management.data['daily_limit'] and high_priority:
        return False

    if email_management.data['sent_this_month'] > email_management.data['monthly_limit']:
        return False

    email_management.save()
    return True


resend.api_key = RESEND_TOKEN


def application_accepted(recipient, username):
    with open("email_templates/application_accepted.html") as f:
        content = f.read()

    content = content.replace("%username%", username)

    params = {
        "from": "Red Lion Studios <no-reply@rlsanimation.com>",
        "to": [recipient],
        "subject": "We have good news for you!",
        "html": content,
        "headers": {
            'X-Entity-Ref-ID': uuid.uuid4().__str__(),
        },
    }
    if increment_and_check_limits():
        resend.Emails.send(resend.Emails.SendParams(**params))

        return True
    return False


def application_rejected(recipient, username):
    with open("email_templates/application_rejected.html") as f:
        content = f.read()

    content = content.replace("%username%", username)

    params = {
        "from": "Red Lion Studios <no-reply@rlsanimation.com>",
        "to": [recipient],
        "subject": "We are really sorry!",
        "html": content,
        "headers": {
            'X-Entity-Ref-ID': uuid.uuid4().__str__(),
        },
    }
    if increment_and_check_limits():
        resend.Emails.send(resend.Emails.SendParams(**params))

        return True
    return False


def password_reset(recipient, username, code):
    with open("email_templates/password_reset.html") as f:
        content = f.read()

    content = (content
               .replace("%username%", username)
               .replace("%code%", code))

    params = {
        "from": "Red Lion Studios <no-reply@rlsanimation.com>",
        "to": [recipient],
        "subject": "Reset your password",
        "html": content,
        "headers": {
            'X-Entity-Ref-ID': uuid.uuid4().__str__(),
        },
    }
    if increment_and_check_limits():
        resend.Emails.send(resend.Emails.SendParams(**params))

        return True
    return False
