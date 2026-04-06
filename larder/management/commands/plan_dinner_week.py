from django.core.management.base import BaseCommand
from datetime import date, timedelta, datetime
from larder.models import Menu, MealPlan, MealPlanDay, Recipe
from larder.meal_planning_service import MealPlanGenerator


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int)
        parser.add_argument('--start-date', default='2026-04-06')
    
    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=options['user_id'])
        
        generator = MealPlanGenerator(user=user)
        start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
        end_date = start_date + timedelta(days=6)  # 7 days total
        
        meal_plan = generator.generate_meal_plan(
            name="Weekly Dinner Plan",
            start_date=start_date,
            end_date=end_date,
            time_period='weekly'
        )
        self.stdout.write(f"✓ Created: {meal_plan.name}")