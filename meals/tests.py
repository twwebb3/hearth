from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import MealPlan, MealRating, Recipe


class WeekViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")

    def test_week_view_returns_200(self):
        """Week view returns 200 for authenticated user."""
        response = self.client.get(reverse("meals:week"))
        self.assertEqual(response.status_code, 200)

    def test_week_view_requires_login(self):
        """Week view redirects to login for anonymous user."""
        self.client.logout()
        response = self.client.get(reverse("meals:week"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


class MealPlanEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")

    def test_meal_pick_creates_meal_plan(self):
        """Picking a date creates a MealPlan if one doesn't exist."""
        test_date = date(2026, 2, 15)
        self.assertFalse(MealPlan.objects.filter(date=test_date).exists())

        response = self.client.get(
            reverse("meals:meal_plan_pick", kwargs={"date_str": "2026-02-15"})
        )

        # Should redirect to edit page
        self.assertEqual(response.status_code, 302)

        # MealPlan should now exist
        self.assertTrue(MealPlan.objects.filter(date=test_date).exists())
        meal_plan = MealPlan.objects.get(date=test_date)
        self.assertEqual(meal_plan.created_by, self.user)
        self.assertEqual(meal_plan.status, "DRAFT")


class FinalizeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.meal_plan = MealPlan.objects.create(
            date=date(2026, 3, 10),
            created_by=self.user,
            status="DRAFT",
        )

    def test_finalize_sets_status(self):
        """Finalizing a meal plan sets status to FINALIZED."""
        response = self.client.post(
            reverse("meals:meal_plan_finalize", kwargs={"pk": self.meal_plan.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.meal_plan.refresh_from_db()
        self.assertEqual(self.meal_plan.status, "FINALIZED")

    def test_finalized_meal_plan_cannot_be_edited(self):
        """Editing a finalized meal plan redirects to detail page."""
        self.meal_plan.status = "FINALIZED"
        self.meal_plan.save()

        response = self.client.get(
            reverse("meals:meal_plan_edit", kwargs={"pk": self.meal_plan.pk})
        )

        # Should redirect to detail page
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("meals:meal_plan_detail", kwargs={"pk": self.meal_plan.pk}),
            response.url,
        )

    def test_unfinalize_allows_editing(self):
        """Unfinalizing a meal plan allows editing again."""
        self.meal_plan.status = "FINALIZED"
        self.meal_plan.save()

        response = self.client.post(
            reverse("meals:meal_plan_unfinalize", kwargs={"pk": self.meal_plan.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.meal_plan.refresh_from_db()
        self.assertEqual(self.meal_plan.status, "DRAFT")


class RatingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.meal_plan = MealPlan.objects.create(
            date=date(2026, 4, 5),
            created_by=self.user,
            status="FINALIZED",
        )

    def test_create_rating(self):
        """Posting to rate view creates a MealRating."""
        self.assertFalse(MealRating.objects.filter(meal_plan=self.meal_plan).exists())

        response = self.client.post(
            reverse("meals:meal_plan_rate", kwargs={"pk": self.meal_plan.pk}),
            data={
                "rating": "4",
                "would_repeat": "on",
                "comment": "Great meal!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(MealRating.objects.filter(meal_plan=self.meal_plan).exists())

        rating = MealRating.objects.get(meal_plan=self.meal_plan)
        self.assertEqual(rating.rating, 4)
        self.assertTrue(rating.would_repeat)
        self.assertEqual(rating.comment, "Great meal!")

    def test_update_rating(self):
        """Posting to rate view updates an existing MealRating."""
        MealRating.objects.create(
            meal_plan=self.meal_plan,
            rating=3,
            would_repeat=False,
            comment="Okay",
        )

        response = self.client.post(
            reverse("meals:meal_plan_rate", kwargs={"pk": self.meal_plan.pk}),
            data={
                "rating": "5",
                "would_repeat": "on",
                "comment": "Actually amazing!",
            },
        )

        self.assertEqual(response.status_code, 302)

        # Should still be only one rating
        self.assertEqual(MealRating.objects.filter(meal_plan=self.meal_plan).count(), 1)

        rating = MealRating.objects.get(meal_plan=self.meal_plan)
        self.assertEqual(rating.rating, 5)
        self.assertTrue(rating.would_repeat)
        self.assertEqual(rating.comment, "Actually amazing!")


class RecipeListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")

        # Create test recipes
        Recipe.objects.create(name="Chicken", kind="MAIN", active=True)
        Recipe.objects.create(name="Pasta", kind="MAIN", active=True)
        Recipe.objects.create(name="Salad", kind="SIDE", active=True)
        Recipe.objects.create(name="Rice", kind="SIDE", active=True)
        Recipe.objects.create(name="Old Recipe", kind="MAIN", active=False)

    def test_recipe_list_returns_all(self):
        """Recipe list returns all recipes without filter."""
        response = self.client.get(reverse("meals:recipe_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["recipes"]), 5)

    def test_recipe_list_filters_by_kind_main(self):
        """Recipe list filters by kind=MAIN."""
        response = self.client.get(reverse("meals:recipe_list"), {"kind": "MAIN"})

        self.assertEqual(response.status_code, 200)
        recipes = response.context["recipes"]
        self.assertEqual(len(recipes), 3)
        for recipe in recipes:
            self.assertEqual(recipe.kind, "MAIN")

    def test_recipe_list_filters_by_kind_side(self):
        """Recipe list filters by kind=SIDE."""
        response = self.client.get(reverse("meals:recipe_list"), {"kind": "SIDE"})

        self.assertEqual(response.status_code, 200)
        recipes = response.context["recipes"]
        self.assertEqual(len(recipes), 2)
        for recipe in recipes:
            self.assertEqual(recipe.kind, "SIDE")

    def test_recipe_list_filters_by_active(self):
        """Recipe list filters by active status."""
        response = self.client.get(reverse("meals:recipe_list"), {"active": "1"})

        self.assertEqual(response.status_code, 200)
        recipes = response.context["recipes"]
        self.assertEqual(len(recipes), 4)
        for recipe in recipes:
            self.assertTrue(recipe.active)

        response = self.client.get(reverse("meals:recipe_list"), {"active": "0"})
        recipes = response.context["recipes"]
        self.assertEqual(len(recipes), 1)
        self.assertFalse(recipes[0].active)
