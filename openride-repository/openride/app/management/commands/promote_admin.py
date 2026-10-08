from django.core.management.base import BaseCommand,CommandError
from app.models import User,school_email,surname_matches
class Command(BaseCommand):
    help='Povýší již aktivní a ověřený školní účet na správce.'
    def add_arguments(self,parser): parser.add_argument('email')
    def handle(self,*args,**options):
        email=options['email'].strip().lower()
        u=User.objects.filter(email__iexact=email).first()
        if not u or not u.is_active or not u.verified_at or not school_email(u.email) or not surname_matches(u.email,u.last_name):
            raise CommandError('Účet musí být aktivní, ověřený a splňovat pravidlo školního e-mailu a příjmení.')
        u.is_staff=True;u.is_superuser=True;u.save(update_fields=['is_staff','is_superuser'])
        self.stdout.write('Správce byl vytvořen pro ověřený účet.')
