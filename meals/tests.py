from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import Combo, ComboStats, MealPlan, MealRating, Recipe


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


class RebuildCombosTests(TestCase):
    """Tests for the rebuild_combos management command."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.main = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.side = Recipe.objects.create(name="Rice", kind="SIDE")
        self.main2 = Recipe.objects.create(name="Salmon", kind="MAIN")
        self.side2 = Recipe.objects.create(name="Salad", kind="SIDE")

    def _make_rated_plan(self, main, side, plan_date, rating, would_repeat,
                         status="FINALIZED"):
        mp = MealPlan.objects.create(
            date=plan_date,
            main_recipe=main,
            side_recipe=side,
            status=status,
            created_by=self.user,
        )
        MealRating.objects.create(
            meal_plan=mp,
            rating=rating,
            would_repeat=would_repeat,
        )
        return mp

    # ------------------------------------------------------------------
    # core correctness
    # ------------------------------------------------------------------

    def test_stats_computed_correctly(self):
        """times_made, avg_rating, would_repeat_rate, last_made_at are exact."""
        self._make_rated_plan(self.main, self.side, date(2026, 1, 1), 4, True)
        self._make_rated_plan(self.main, self.side, date(2026, 1, 8), 2, False)
        self._make_rated_plan(self.main, self.side, date(2026, 1, 15), 3, True)

        call_command("rebuild_combos")

        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        stats = combo.stats

        self.assertEqual(stats.times_made, 3)
        self.assertAlmostEqual(stats.avg_rating, 3.0)  # (4+2+3)/3
        self.assertAlmostEqual(stats.would_repeat_rate, 0.67, places=2)  # 2/3
        self.assertEqual(stats.last_made_at, date(2026, 1, 15))

    # ------------------------------------------------------------------
    # idempotency
    # ------------------------------------------------------------------

    def test_idempotent_double_run(self):
        """Running the command twice produces identical stats."""
        self._make_rated_plan(self.main, self.side, date(2026, 2, 1), 5, True)
        self._make_rated_plan(self.main, self.side, date(2026, 2, 8), 3, False)

        call_command("rebuild_combos")
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        first = (
            combo.stats.times_made,
            combo.stats.avg_rating,
            combo.stats.would_repeat_rate,
            combo.stats.last_made_at,
        )

        call_command("rebuild_combos")
        combo.stats.refresh_from_db()
        second = (
            combo.stats.times_made,
            combo.stats.avg_rating,
            combo.stats.would_repeat_rate,
            combo.stats.last_made_at,
        )

        self.assertEqual(first, second)
        self.assertEqual(Combo.objects.count(), 1)
        self.assertEqual(ComboStats.objects.count(), 1)

    # ------------------------------------------------------------------
    # mutation – stats update after data changes
    # ------------------------------------------------------------------

    def test_stats_update_after_new_plan(self):
        """Adding a new rated plan and re-running updates all stats."""
        self._make_rated_plan(self.main, self.side, date(2026, 3, 1), 4, True)

        call_command("rebuild_combos")
        stats = Combo.objects.get(main_recipe=self.main, side_recipe=self.side).stats
        self.assertEqual(stats.times_made, 1)
        self.assertAlmostEqual(stats.avg_rating, 4.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 1.0)
        self.assertEqual(stats.last_made_at, date(2026, 3, 1))

        # add a second plan
        self._make_rated_plan(self.main, self.side, date(2026, 3, 8), 2, False)

        call_command("rebuild_combos")
        stats.refresh_from_db()
        self.assertEqual(stats.times_made, 2)
        self.assertAlmostEqual(stats.avg_rating, 3.0)  # (4+2)/2
        self.assertAlmostEqual(stats.would_repeat_rate, 0.5)  # 1/2
        self.assertEqual(stats.last_made_at, date(2026, 3, 8))

    # ------------------------------------------------------------------
    # exclusion – non-qualifying plans are ignored
    # ------------------------------------------------------------------

    def test_draft_plans_excluded(self):
        """DRAFT meal plans are not counted even if rated."""
        self._make_rated_plan(self.main, self.side, date(2026, 4, 1), 5, True)
        self._make_rated_plan(
            self.main, self.side, date(2026, 4, 8), 1, False, status="DRAFT"
        )

        call_command("rebuild_combos")
        stats = Combo.objects.get(main_recipe=self.main, side_recipe=self.side).stats

        self.assertEqual(stats.times_made, 1)
        self.assertAlmostEqual(stats.avg_rating, 5.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 1.0)
        self.assertEqual(stats.last_made_at, date(2026, 4, 1))

    def test_unrated_plans_excluded(self):
        """Finalized plans without a MealRating are not counted."""
        self._make_rated_plan(self.main, self.side, date(2026, 5, 1), 3, True)
        # finalized but no rating
        MealPlan.objects.create(
            date=date(2026, 5, 8),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )

        call_command("rebuild_combos")
        stats = Combo.objects.get(main_recipe=self.main, side_recipe=self.side).stats
        self.assertEqual(stats.times_made, 1)

    def test_plans_missing_side_excluded(self):
        """Plans with only a main recipe do not produce a combo."""
        mp = MealPlan.objects.create(
            date=date(2026, 6, 1),
            main_recipe=self.main,
            side_recipe=None,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=4, would_repeat=True)

        call_command("rebuild_combos")
        self.assertEqual(Combo.objects.count(), 0)

    # ------------------------------------------------------------------
    # multiple combos stay independent
    # ------------------------------------------------------------------

    def test_multiple_combos_independent(self):
        """Two different pairings get separate Combo+Stats rows."""
        self._make_rated_plan(self.main, self.side, date(2026, 7, 1), 5, True)
        self._make_rated_plan(self.main2, self.side2, date(2026, 7, 2), 1, False)

        call_command("rebuild_combos")

        self.assertEqual(Combo.objects.count(), 2)

        s1 = Combo.objects.get(main_recipe=self.main, side_recipe=self.side).stats
        s2 = Combo.objects.get(main_recipe=self.main2, side_recipe=self.side2).stats

        self.assertEqual(s1.times_made, 1)
        self.assertAlmostEqual(s1.avg_rating, 5.0)
        self.assertAlmostEqual(s1.would_repeat_rate, 1.0)

        self.assertEqual(s2.times_made, 1)
        self.assertAlmostEqual(s2.avg_rating, 1.0)
        self.assertAlmostEqual(s2.would_repeat_rate, 0.0)

    def test_no_qualifying_plans(self):
        """Command handles empty dataset gracefully."""
        call_command("rebuild_combos")
        self.assertEqual(Combo.objects.count(), 0)
        self.assertEqual(ComboStats.objects.count(), 0)


class ComboSignalTests(TestCase):
    """Signals auto-upsert Combo and refresh ComboStats on every relevant change."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.main = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.side = Recipe.objects.create(name="Rice", kind="SIDE")

    def _get_stats(self):
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        return combo.stats

    # ------------------------------------------------------------------
    # MealPlan finalize / unfinalize
    # ------------------------------------------------------------------

    def test_finalize_with_rating_creates_combo_and_stats(self):
        """Finalizing a rated plan auto-creates the Combo and correct stats."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 1),
            main_recipe=self.main,
            side_recipe=self.side,
            status="DRAFT",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=4, would_repeat=True)

        # Finalize — triggers post_save on MealPlan
        mp.status = "FINALIZED"
        mp.save()

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 1)
        self.assertAlmostEqual(stats.avg_rating, 4.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 1.0)
        self.assertEqual(stats.last_made_at, date(2026, 8, 1))

    def test_unfinalize_updates_stats(self):
        """Unfinalizing drops the plan from stats."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 2),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=5, would_repeat=True)

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 1)

        # Unfinalize — triggers post_save on MealPlan
        mp.status = "DRAFT"
        mp.save()

        stats.refresh_from_db()
        self.assertEqual(stats.times_made, 0)
        self.assertAlmostEqual(stats.avg_rating, 0.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 0.0)
        self.assertIsNone(stats.last_made_at)

    # ------------------------------------------------------------------
    # MealRating create / update / delete
    # ------------------------------------------------------------------

    def test_rating_create_updates_stats(self):
        """Creating a rating on a finalized plan refreshes stats."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 3),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        # Combo exists but times_made is 0 (no rating yet)
        stats = self._get_stats()
        self.assertEqual(stats.times_made, 0)

        MealRating.objects.create(meal_plan=mp, rating=3, would_repeat=False)

        stats.refresh_from_db()
        self.assertEqual(stats.times_made, 1)
        self.assertAlmostEqual(stats.avg_rating, 3.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 0.0)
        self.assertEqual(stats.last_made_at, date(2026, 8, 3))

    def test_rating_update_updates_stats(self):
        """Updating a rating value refreshes stats."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 4),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        rating = MealRating.objects.create(meal_plan=mp, rating=2, would_repeat=False)

        stats = self._get_stats()
        self.assertAlmostEqual(stats.avg_rating, 2.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 0.0)

        rating.rating = 5
        rating.would_repeat = True
        rating.save()

        stats.refresh_from_db()
        self.assertAlmostEqual(stats.avg_rating, 5.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 1.0)

    def test_rating_delete_updates_stats(self):
        """Deleting a rating refreshes stats (times_made drops)."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 5),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        rating = MealRating.objects.create(meal_plan=mp, rating=4, would_repeat=True)

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 1)

        rating.delete()

        stats.refresh_from_db()
        self.assertEqual(stats.times_made, 0)
        self.assertAlmostEqual(stats.avg_rating, 0.0)
        self.assertIsNone(stats.last_made_at)

    # ------------------------------------------------------------------
    # edge cases
    # ------------------------------------------------------------------

    def test_no_combo_when_side_missing(self):
        """No combo is created when the plan has no side recipe."""
        MealPlan.objects.create(
            date=date(2026, 8, 6),
            main_recipe=self.main,
            side_recipe=None,
            status="FINALIZED",
            created_by=self.user,
        )
        self.assertEqual(Combo.objects.count(), 0)

    def test_no_combo_when_main_missing(self):
        """No combo is created when the plan has no main recipe."""
        MealPlan.objects.create(
            date=date(2026, 8, 7),
            main_recipe=None,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        self.assertEqual(Combo.objects.count(), 0)

    def test_multiple_plans_accumulate(self):
        """Stats reflect all qualifying plans for the pair."""
        mp1 = MealPlan.objects.create(
            date=date(2026, 8, 10),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp1, rating=4, would_repeat=True)

        mp2 = MealPlan.objects.create(
            date=date(2026, 8, 17),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp2, rating=2, would_repeat=False)

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 2)
        self.assertAlmostEqual(stats.avg_rating, 3.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 0.5)
        self.assertEqual(stats.last_made_at, date(2026, 8, 17))

    # ------------------------------------------------------------------
    # end-to-end combo creation
    # ------------------------------------------------------------------

    def test_finalized_plan_then_rated_creates_combo(self):
        """Creating a FINALIZED plan then adding a rating produces a Combo."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 20),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        # Combo exists after plan save but times_made is 0 (no rating)
        self.assertTrue(Combo.objects.filter(
            main_recipe=self.main, side_recipe=self.side,
        ).exists())

        MealRating.objects.create(meal_plan=mp, rating=5, would_repeat=True)

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 1)
        self.assertAlmostEqual(stats.avg_rating, 5.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 1.0)
        self.assertEqual(stats.last_made_at, date(2026, 8, 20))

    def test_second_plan_reuses_existing_combo(self):
        """A second finalized+rated plan for the same pair reuses the Combo."""
        mp1 = MealPlan.objects.create(
            date=date(2026, 8, 21),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp1, rating=4, would_repeat=True)

        mp2 = MealPlan.objects.create(
            date=date(2026, 8, 28),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp2, rating=2, would_repeat=False)

        self.assertEqual(Combo.objects.filter(
            main_recipe=self.main, side_recipe=self.side,
        ).count(), 1)

    # ------------------------------------------------------------------
    # multi-plan rating update
    # ------------------------------------------------------------------

    def test_rating_update_recalculates_aggregate(self):
        """Updating one rating in a multi-plan combo recalculates all stats."""
        mp1 = MealPlan.objects.create(
            date=date(2026, 8, 22),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp1, rating=4, would_repeat=True)

        mp2 = MealPlan.objects.create(
            date=date(2026, 8, 29),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        r2 = MealRating.objects.create(meal_plan=mp2, rating=2, would_repeat=False)

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 2)
        self.assertAlmostEqual(stats.avg_rating, 3.0)       # (4+2)/2
        self.assertAlmostEqual(stats.would_repeat_rate, 0.5) # 1/2

        # Update second rating: 2→5, would_repeat False→True
        r2.rating = 5
        r2.would_repeat = True
        r2.save()

        stats.refresh_from_db()
        self.assertEqual(stats.times_made, 2)
        self.assertAlmostEqual(stats.avg_rating, 4.5)       # (4+5)/2
        self.assertAlmostEqual(stats.would_repeat_rate, 1.0) # 2/2
        self.assertEqual(stats.last_made_at, date(2026, 8, 29))

    # ------------------------------------------------------------------
    # multi-plan rating delete (partial and full)
    # ------------------------------------------------------------------

    def test_delete_one_of_two_ratings_updates_stats(self):
        """Deleting one rating from a two-plan combo keeps remaining stats."""
        mp1 = MealPlan.objects.create(
            date=date(2026, 8, 23),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp1, rating=4, would_repeat=True)

        mp2 = MealPlan.objects.create(
            date=date(2026, 8, 30),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        r2 = MealRating.objects.create(meal_plan=mp2, rating=2, would_repeat=False)

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 2)

        r2.delete()

        stats.refresh_from_db()
        self.assertEqual(stats.times_made, 1)
        self.assertAlmostEqual(stats.avg_rating, 4.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 1.0)
        self.assertEqual(stats.last_made_at, date(2026, 8, 23))

    def test_delete_last_rating_zeros_all_stats(self):
        """Deleting the only rating zeros out all four stats fields."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 24),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        rating = MealRating.objects.create(meal_plan=mp, rating=4, would_repeat=True)

        stats = self._get_stats()
        self.assertEqual(stats.times_made, 1)

        rating.delete()

        stats.refresh_from_db()
        self.assertEqual(stats.times_made, 0)
        self.assertAlmostEqual(stats.avg_rating, 0.0)
        self.assertAlmostEqual(stats.would_repeat_rate, 0.0)
        self.assertIsNone(stats.last_made_at)

    def test_combo_persists_after_all_ratings_deleted(self):
        """The Combo and ComboStats rows still exist after all ratings are gone."""
        mp = MealPlan.objects.create(
            date=date(2026, 8, 25),
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        rating = MealRating.objects.create(meal_plan=mp, rating=3, would_repeat=False)

        rating.delete()

        self.assertTrue(Combo.objects.filter(
            main_recipe=self.main, side_recipe=self.side,
        ).exists())
        self.assertTrue(ComboStats.objects.filter(
            combo__main_recipe=self.main, combo__side_recipe=self.side,
        ).exists())


class ComboListViewTests(TestCase):
    """Tests for the /meals/combos/ page."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.main1 = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.main2 = Recipe.objects.create(name="Salmon", kind="MAIN")
        self.side1 = Recipe.objects.create(name="Rice", kind="SIDE")
        self.side2 = Recipe.objects.create(name="Salad", kind="SIDE")

    def _make_rated_plan(self, main, side, plan_date, rating, would_repeat):
        mp = MealPlan.objects.create(
            date=plan_date,
            main_recipe=main,
            side_recipe=side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=rating, would_repeat=would_repeat)
        return mp

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("meals:combo_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_empty_state(self):
        response = self.client.get(reverse("meals:combo_list"), {"show_all": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["combos"]), 0)
        self.assertContains(response, "No combos yet")

    def test_shows_qualified_combos(self):
        self._make_rated_plan(self.main1, self.side1, date(2026, 9, 1), 4, True)
        self._make_rated_plan(self.main2, self.side2, date(2026, 9, 2), 3, False)

        response = self.client.get(reverse("meals:combo_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["combos"]), 2)
        self.assertContains(response, "Chicken")
        self.assertContains(response, "Rice")
        self.assertContains(response, "Salmon")
        self.assertContains(response, "Salad")

    def test_sorted_best_first(self):
        """Higher avg_rating combos appear first."""
        self._make_rated_plan(self.main1, self.side1, date(2026, 9, 3), 3, False)
        self._make_rated_plan(self.main2, self.side2, date(2026, 9, 4), 5, True)

        response = self.client.get(reverse("meals:combo_list"))
        combos = list(response.context["combos"])
        self.assertEqual(combos[0].main_recipe, self.main2)
        self.assertEqual(combos[1].main_recipe, self.main1)

    def test_excludes_unqualified_combos(self):
        """Combos without a finalized+rated plan don't appear."""
        # Draft with rating — not qualified
        mp = MealPlan.objects.create(
            date=date(2026, 9, 5),
            main_recipe=self.main1,
            side_recipe=self.side1,
            status="DRAFT",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=5, would_repeat=True)

        response = self.client.get(reverse("meals:combo_list"))
        self.assertEqual(len(response.context["combos"]), 0)


class ComboDetailViewTests(TestCase):
    """Tests for the /meals/combos/<pk>/ page."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.main = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.side = Recipe.objects.create(name="Rice", kind="SIDE")

    def _make_rated_plan(self, plan_date, rating, would_repeat, comment=""):
        mp = MealPlan.objects.create(
            date=plan_date,
            main_recipe=self.main,
            side_recipe=self.side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(
            meal_plan=mp, rating=rating, would_repeat=would_repeat, comment=comment,
        )
        return mp

    def test_requires_login(self):
        self._make_rated_plan(date(2026, 10, 1), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        self.client.logout()
        response = self.client.get(reverse("meals:combo_detail", kwargs={"pk": combo.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_404_for_missing_combo(self):
        response = self.client.get(reverse("meals:combo_detail", kwargs={"pk": 99999}))
        self.assertEqual(response.status_code, 404)

    def test_shows_stats(self):
        self._make_rated_plan(date(2026, 10, 2), 5, True)
        self._make_rated_plan(date(2026, 10, 9), 3, False)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        response = self.client.get(reverse("meals:combo_detail", kwargs={"pk": combo.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chicken")
        self.assertContains(response, "Rice")
        # times_made
        self.assertContains(response, "2")
        # avg_rating 4.0
        self.assertContains(response, "4.0")

    def test_shows_meal_plan_history(self):
        self._make_rated_plan(date(2026, 10, 3), 4, True, comment="Great combo")
        self._make_rated_plan(date(2026, 10, 10), 2, False, comment="Not as good")
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        response = self.client.get(reverse("meals:combo_detail", kwargs={"pk": combo.pk}))
        self.assertEqual(len(response.context["meal_plans"]), 2)
        self.assertContains(response, "Great combo")
        self.assertContains(response, "Not as good")

    def test_history_ordered_newest_first(self):
        mp1 = self._make_rated_plan(date(2026, 10, 4), 3, True)
        mp2 = self._make_rated_plan(date(2026, 10, 11), 5, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        response = self.client.get(reverse("meals:combo_detail", kwargs={"pk": combo.pk}))
        plans = list(response.context["meal_plans"])
        self.assertEqual(plans[0].pk, mp2.pk)
        self.assertEqual(plans[1].pk, mp1.pk)


class ComboPickerTests(TestCase):
    """Tests for the combo picker on the meal plan edit/create form."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.main = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.side = Recipe.objects.create(name="Rice", kind="SIDE")

    def _make_combo(self, main, side, rating=4, would_repeat=True):
        mp = MealPlan.objects.create(
            date=date(2026, 11, 1 + Combo.objects.count()),
            main_recipe=main,
            side_recipe=side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=rating, would_repeat=would_repeat)

    def test_edit_page_shows_combo_picker(self):
        """The combo picker appears on the edit page when combos exist."""
        self._make_combo(self.main, self.side)
        plan = MealPlan.objects.create(
            date=date(2026, 11, 20),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.get(reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose from combos")
        self.assertContains(response, "Chicken + Rice")
        self.assertContains(response, "id_combo_picker")

    def test_edit_page_hides_picker_when_no_combos(self):
        """The combo picker is absent when there are no qualified combos."""
        plan = MealPlan.objects.create(
            date=date(2026, 11, 21),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.get(reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Choose from combos")

    def test_picker_has_data_attributes(self):
        """Each combo option carries data-main-id and data-side-id."""
        self._make_combo(self.main, self.side)
        plan = MealPlan.objects.create(
            date=date(2026, 11, 22),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.get(reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}))
        self.assertContains(response, f'data-main-id="{self.main.pk}"')
        self.assertContains(response, f'data-side-id="{self.side.pk}"')

    def test_inactive_recipe_combos_excluded(self):
        """Combos with an inactive recipe don't appear in the picker."""
        self._make_combo(self.main, self.side)
        self.side.active = False
        self.side.save()

        plan = MealPlan.objects.create(
            date=date(2026, 11, 23),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.get(reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}))
        self.assertNotContains(response, "Choose from combos")

    def test_create_page_shows_combo_picker(self):
        """The combo picker also appears on the create page."""
        self._make_combo(self.main, self.side)

        response = self.client.get(reverse("meals:meal_plan_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose from combos")
        self.assertContains(response, "Chicken + Rice")

    def test_manual_override_still_works(self):
        """Manually selecting recipes still submits correctly (combo is not a form field)."""
        self._make_combo(self.main, self.side)
        side2 = Recipe.objects.create(name="Salad", kind="SIDE")
        plan = MealPlan.objects.create(
            date=date(2026, 11, 24),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.post(
            reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}),
            data={
                "date": "2026-11-24",
                "main_recipe": str(self.main.pk),
                "side_recipe": str(side2.pk),
                "notes": "",
                "status": "DRAFT",
            },
        )
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.main_recipe, self.main)
        self.assertEqual(plan.side_recipe, side2)


class SuggestTopComboTests(TestCase):
    """Tests for the suggest_top_combo service function."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.main1 = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.main2 = Recipe.objects.create(name="Salmon", kind="MAIN")
        self.side1 = Recipe.objects.create(name="Rice", kind="SIDE")
        self.side2 = Recipe.objects.create(name="Salad", kind="SIDE")

    def _make_rated_plan(self, main, side, plan_date, rating, would_repeat):
        mp = MealPlan.objects.create(
            date=plan_date,
            main_recipe=main,
            side_recipe=side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=rating, would_repeat=would_repeat)
        return mp

    def test_returns_best_combo(self):
        """Returns the highest-ranked combo when none are on cooldown."""
        from .services import suggest_top_combo

        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 3, False)
        self._make_rated_plan(self.main2, self.side2, date(2025, 6, 2), 5, True)

        combo = suggest_top_combo(today=date(2026, 1, 1))
        self.assertIsNotNone(combo)
        self.assertEqual(combo.main_recipe, self.main2)
        self.assertEqual(combo.side_recipe, self.side2)

    def test_skips_recently_used_combo(self):
        """A combo used within the cooldown window is skipped."""
        from .services import suggest_top_combo

        # Best combo used 5 days ago (within 14-day cooldown)
        self._make_rated_plan(self.main1, self.side1, date(2026, 1, 10), 5, True)
        # Second-best combo used long ago
        self._make_rated_plan(self.main2, self.side2, date(2025, 6, 1), 3, True)

        combo = suggest_top_combo(today=date(2026, 1, 15))
        self.assertIsNotNone(combo)
        self.assertEqual(combo.main_recipe, self.main2)

    def test_returns_none_when_all_on_cooldown(self):
        """Returns None when every qualified combo was used recently."""
        from .services import suggest_top_combo

        self._make_rated_plan(self.main1, self.side1, date(2026, 1, 10), 5, True)

        combo = suggest_top_combo(today=date(2026, 1, 15))
        self.assertIsNone(combo)

    def test_returns_none_when_no_combos(self):
        """Returns None when there are no qualified combos at all."""
        from .services import suggest_top_combo

        combo = suggest_top_combo(today=date(2026, 1, 1))
        self.assertIsNone(combo)

    def test_draft_plan_triggers_cooldown(self):
        """Even a DRAFT plan within the window triggers the cooldown."""
        from .services import suggest_top_combo

        # Qualified via old finalized+rated plan
        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 5, True)
        # Recent draft for the same pair
        MealPlan.objects.create(
            date=date(2026, 1, 10),
            main_recipe=self.main1,
            side_recipe=self.side1,
            status="DRAFT",
            created_by=self.user,
        )

        combo = suggest_top_combo(today=date(2026, 1, 15))
        self.assertIsNone(combo)

    def test_combo_available_after_cooldown_expires(self):
        """A combo becomes available again once the cooldown period passes."""
        from .services import suggest_top_combo

        self._make_rated_plan(self.main1, self.side1, date(2026, 1, 1), 5, True)

        # Day 14 — still on cooldown (cutoff = today - 14 = Jan 1, date >= Jan 1)
        self.assertIsNone(suggest_top_combo(today=date(2026, 1, 15)))

        # Day 16 — cooldown expired (cutoff = Jan 2, plan date Jan 1 < Jan 2)
        combo = suggest_top_combo(today=date(2026, 1, 16))
        self.assertIsNotNone(combo)
        self.assertEqual(combo.main_recipe, self.main1)

    def test_excludes_inactive_recipes(self):
        """Combos with an inactive recipe are not suggested."""
        from .services import suggest_top_combo

        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 5, True)
        self.side1.active = False
        self.side1.save()

        combo = suggest_top_combo(today=date(2026, 1, 1))
        self.assertIsNone(combo)

    # ------------------------------------------------------------------
    # recently-used exclusion / cooldown edge cases
    # ------------------------------------------------------------------

    def test_unrated_finalized_plan_triggers_cooldown(self):
        """A finalized plan with no rating still triggers cooldown."""
        from .services import suggest_top_combo

        # Old rated plan to qualify the combo
        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 5, True)
        # Recent finalized plan with same pair, no rating
        MealPlan.objects.create(
            date=date(2026, 1, 10),
            main_recipe=self.main1,
            side_recipe=self.side1,
            status="FINALIZED",
            created_by=self.user,
        )

        self.assertIsNone(suggest_top_combo(today=date(2026, 1, 15)))

    def test_cooldown_targets_specific_recipe_pair(self):
        """A recent plan for one recipe pair doesn't block a different pair."""
        from .services import suggest_top_combo

        # Two combos, both rated well in the past
        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 5, True)
        self._make_rated_plan(self.main2, self.side2, date(2025, 6, 2), 4, True)
        # Recent plan only for main1+side1
        MealPlan.objects.create(
            date=date(2026, 1, 10),
            main_recipe=self.main1,
            side_recipe=self.side1,
            status="DRAFT",
            created_by=self.user,
        )

        combo = suggest_top_combo(today=date(2026, 1, 15))
        self.assertIsNotNone(combo)
        self.assertEqual(combo.main_recipe, self.main2)
        self.assertEqual(combo.side_recipe, self.side2)

    def test_multiple_combos_returns_best_available(self):
        """Among non-cooldown combos, the highest-ranked one is returned."""
        from .services import suggest_top_combo

        main3 = Recipe.objects.create(name="Beef", kind="MAIN")
        # Best combo (rating 5) — on cooldown
        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 5, True)
        MealPlan.objects.create(
            date=date(2026, 1, 10),
            main_recipe=self.main1,
            side_recipe=self.side1,
            status="DRAFT",
            created_by=self.user,
        )
        # Second-best combo (rating 4) — available
        self._make_rated_plan(self.main2, self.side2, date(2025, 6, 2), 4, True)
        # Third combo (rating 3) — available
        self._make_rated_plan(main3, self.side2, date(2025, 6, 3), 3, True)

        combo = suggest_top_combo(today=date(2026, 1, 15))
        self.assertIsNotNone(combo)
        self.assertEqual(combo.main_recipe, self.main2)
        self.assertEqual(combo.side_recipe, self.side2)

    def test_all_combos_on_cooldown_returns_none(self):
        """Returns None when every qualified combo has a recent plan."""
        from .services import suggest_top_combo

        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 5, True)
        self._make_rated_plan(self.main2, self.side2, date(2025, 6, 2), 4, True)
        # Both combos used recently
        MealPlan.objects.create(
            date=date(2026, 1, 10),
            main_recipe=self.main1,
            side_recipe=self.side1,
            status="DRAFT",
            created_by=self.user,
        )
        MealPlan.objects.create(
            date=date(2026, 1, 12),
            main_recipe=self.main2,
            side_recipe=self.side2,
            status="DRAFT",
            created_by=self.user,
        )

        self.assertIsNone(suggest_top_combo(today=date(2026, 1, 15)))

    def test_shared_main_recipe_independent_cooldowns(self):
        """Two combos sharing a main recipe but different sides have
        independent cooldowns."""
        from .services import suggest_top_combo

        side3 = Recipe.objects.create(name="Mashed Potatoes", kind="SIDE")
        # Combo A: main1 + side1
        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 5, True)
        # Combo B: main1 + side3
        self._make_rated_plan(self.main1, side3, date(2025, 6, 2), 4, True)
        # Only combo A used recently
        MealPlan.objects.create(
            date=date(2026, 1, 10),
            main_recipe=self.main1,
            side_recipe=self.side1,
            status="DRAFT",
            created_by=self.user,
        )

        combo = suggest_top_combo(today=date(2026, 1, 15))
        self.assertIsNotNone(combo)
        self.assertEqual(combo.main_recipe, self.main1)
        self.assertEqual(combo.side_recipe, side3)


class PickTopComboViewTests(TestCase):
    """Tests for the pick_top_combo view (POST endpoint)."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.main = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.side = Recipe.objects.create(name="Rice", kind="SIDE")

    def _make_qualified_combo(self, main, side, plan_date=None, rating=5):
        """Create a finalized+rated plan so the combo qualifies, dated far in the past."""
        mp = MealPlan.objects.create(
            date=plan_date or date(2025, 1, 1),
            main_recipe=main,
            side_recipe=side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=rating, would_repeat=True)

    def test_sets_recipes_and_redirects(self):
        """POST fills the meal plan with the top combo and redirects to edit."""
        self._make_qualified_combo(self.main, self.side)
        plan = MealPlan.objects.create(
            date=date(2026, 3, 1),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.post(
            reverse("meals:pick_top_combo", kwargs={"pk": plan.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}),
            response.url,
        )
        plan.refresh_from_db()
        self.assertEqual(plan.main_recipe, self.main)
        self.assertEqual(plan.side_recipe, self.side)

    def test_get_not_allowed(self):
        """GET requests are rejected with 405."""
        plan = MealPlan.objects.create(
            date=date(2026, 3, 2),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.get(
            reverse("meals:pick_top_combo", kwargs={"pk": plan.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_404_for_missing_plan(self):
        """Returns 404 for a nonexistent meal plan."""
        response = self.client.post(
            reverse("meals:pick_top_combo", kwargs={"pk": 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_finalized_plan_redirects_to_detail(self):
        """A finalized plan cannot have its combo changed."""
        self._make_qualified_combo(self.main, self.side)
        plan = MealPlan.objects.create(
            date=date(2026, 3, 3),
            created_by=self.user,
            status="FINALIZED",
        )

        response = self.client.post(
            reverse("meals:pick_top_combo", kwargs={"pk": plan.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("meals:meal_plan_detail", kwargs={"pk": plan.pk}),
            response.url,
        )

    def test_no_suggestion_redirects_to_edit(self):
        """When no combo is available, redirects back to edit with info message."""
        plan = MealPlan.objects.create(
            date=date(2026, 3, 4),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.post(
            reverse("meals:pick_top_combo", kwargs={"pk": plan.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}),
            response.url,
        )

    def test_requires_login(self):
        """Anonymous users are redirected to login."""
        plan = MealPlan.objects.create(
            date=date(2026, 3, 5),
            created_by=self.user,
            status="DRAFT",
        )
        self.client.logout()

        response = self.client.post(
            reverse("meals:pick_top_combo", kwargs={"pk": plan.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_view_skips_recently_used_combo(self):
        """pick_top_combo view skips combos on cooldown and picks next best."""
        today = date.today()
        main2 = Recipe.objects.create(name="Salmon", kind="MAIN")
        side2 = Recipe.objects.create(name="Salad", kind="SIDE")
        # Best combo (rating 5), but used today → on cooldown
        self._make_qualified_combo(self.main, self.side, plan_date=date(2025, 1, 1))
        MealPlan.objects.create(
            date=today,
            main_recipe=self.main,
            side_recipe=self.side,
            status="DRAFT",
            created_by=self.user,
        )
        # Second-best combo (rating 4), available
        self._make_qualified_combo(main2, side2, plan_date=date(2025, 1, 2), rating=4)

        plan = MealPlan.objects.create(
            date=today + timedelta(days=1),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.post(
            reverse("meals:pick_top_combo", kwargs={"pk": plan.pk})
        )
        plan.refresh_from_db()
        self.assertEqual(plan.main_recipe, main2)
        self.assertEqual(plan.side_recipe, side2)


class ComboVisibilityTests(TestCase):
    """Tests for combo visibility rules: times_made>=1 and min_rating filtering."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.main1 = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.main2 = Recipe.objects.create(name="Salmon", kind="MAIN")
        self.side1 = Recipe.objects.create(name="Rice", kind="SIDE")
        self.side2 = Recipe.objects.create(name="Salad", kind="SIDE")

    def _make_rated_plan(self, main, side, plan_date, rating, would_repeat):
        mp = MealPlan.objects.create(
            date=plan_date,
            main_recipe=main,
            side_recipe=side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=rating, would_repeat=would_repeat)
        return mp

    # ------------------------------------------------------------------
    # service-level: get_qualified_combos
    # ------------------------------------------------------------------

    def test_times_made_zero_excluded(self):
        """A combo with times_made=0 in stats is excluded even if qualified() matches."""
        from .services import get_qualified_combos

        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 1), 4, True)
        combo = Combo.objects.get(main_recipe=self.main1, side_recipe=self.side1)

        # Artificially zero out times_made to simulate stale stats
        combo.stats.times_made = 0
        combo.stats.save()

        combos = list(get_qualified_combos())
        self.assertEqual(len(combos), 0)

    def test_min_rating_filters_low_rated(self):
        """min_rating excludes combos below the threshold."""
        from .services import get_qualified_combos

        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 2), 2, False)
        self._make_rated_plan(self.main2, self.side2, date(2026, 5, 3), 4, True)

        combos = list(get_qualified_combos(min_rating=3))
        self.assertEqual(len(combos), 1)
        self.assertEqual(combos[0].main_recipe, self.main2)

    def test_min_rating_none_shows_all(self):
        """min_rating=None returns all combos regardless of rating."""
        from .services import get_qualified_combos

        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 4), 1, False)
        self._make_rated_plan(self.main2, self.side2, date(2026, 5, 5), 5, True)

        combos = list(get_qualified_combos(min_rating=None))
        self.assertEqual(len(combos), 2)

    def test_min_rating_boundary_included(self):
        """A combo with avg_rating exactly equal to min_rating is included."""
        from .services import get_qualified_combos

        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 6), 3, True)

        combos = list(get_qualified_combos(min_rating=3))
        self.assertEqual(len(combos), 1)

    # ------------------------------------------------------------------
    # combo list view: default filter vs show_all
    # ------------------------------------------------------------------

    def test_combo_list_hides_low_rated_by_default(self):
        """Combo list hides combos with avg_rating < 3 by default."""
        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 7), 2, False)
        self._make_rated_plan(self.main2, self.side2, date(2026, 5, 8), 4, True)

        response = self.client.get(reverse("meals:combo_list"))
        self.assertEqual(response.status_code, 200)
        combos = list(response.context["combos"])
        self.assertEqual(len(combos), 1)
        self.assertEqual(combos[0].main_recipe, self.main2)
        self.assertContains(response, "rated 3+")

    def test_combo_list_show_all_includes_low_rated(self):
        """show_all=1 includes combos with avg_rating < 3."""
        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 9), 2, False)
        self._make_rated_plan(self.main2, self.side2, date(2026, 5, 10), 4, True)

        response = self.client.get(reverse("meals:combo_list"), {"show_all": "1"})
        self.assertEqual(response.status_code, 200)
        combos = list(response.context["combos"])
        self.assertEqual(len(combos), 2)
        self.assertTrue(response.context["show_all"])
        self.assertNotContains(response, "rated 3+")

    def test_combo_list_show_all_toggle_link(self):
        """Default view shows 'Show all' link; show_all view shows 'Hide low-rated'."""
        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 11), 4, True)

        response = self.client.get(reverse("meals:combo_list"))
        self.assertContains(response, "Show all")
        self.assertNotContains(response, "Hide low-rated")

        response = self.client.get(reverse("meals:combo_list"), {"show_all": "1"})
        self.assertContains(response, "Hide low-rated")

    def test_combo_list_empty_filtered_shows_hint(self):
        """When all combos are below rating 3, the empty state suggests 'Show all'."""
        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 12), 1, False)

        response = self.client.get(reverse("meals:combo_list"))
        self.assertEqual(len(response.context["combos"]), 0)
        self.assertContains(response, "No combos rated 3 or above")
        self.assertContains(response, "show_all=1")

    # ------------------------------------------------------------------
    # combo picker on meal plan form
    # ------------------------------------------------------------------

    def test_picker_excludes_low_rated_combos(self):
        """The combo picker on the edit form excludes combos rated below 3."""
        self._make_rated_plan(self.main1, self.side1, date(2026, 5, 13), 2, False)
        self._make_rated_plan(self.main2, self.side2, date(2026, 5, 14), 4, True)
        plan = MealPlan.objects.create(
            date=date(2026, 5, 20),
            created_by=self.user,
            status="DRAFT",
        )

        response = self.client.get(reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk}))
        self.assertContains(response, "Salmon + Salad")
        self.assertNotContains(response, "Chicken + Rice")

    # ------------------------------------------------------------------
    # suggest_top_combo
    # ------------------------------------------------------------------

    def test_suggest_skips_low_rated_combos(self):
        """suggest_top_combo does not return combos rated below 3."""
        from .services import suggest_top_combo

        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 2, False)

        combo = suggest_top_combo(today=date(2026, 5, 1))
        self.assertIsNone(combo)

    def test_suggest_returns_combo_rated_3_or_above(self):
        """suggest_top_combo returns combos rated 3 or above."""
        from .services import suggest_top_combo

        self._make_rated_plan(self.main1, self.side1, date(2025, 6, 1), 2, False)
        self._make_rated_plan(self.main2, self.side2, date(2025, 6, 2), 3, True)

        combo = suggest_top_combo(today=date(2026, 5, 1))
        self.assertIsNotNone(combo)
        self.assertEqual(combo.main_recipe, self.main2)


class ComboArchiveTests(TestCase):
    """Tests for the combo archive/unarchive feature."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")
        self.main = Recipe.objects.create(name="Chicken", kind="MAIN")
        self.side = Recipe.objects.create(name="Rice", kind="SIDE")

    def _make_rated_plan(self, main, side, plan_date, rating, would_repeat):
        mp = MealPlan.objects.create(
            date=plan_date,
            main_recipe=main,
            side_recipe=side,
            status="FINALIZED",
            created_by=self.user,
        )
        MealRating.objects.create(meal_plan=mp, rating=rating, would_repeat=would_repeat)
        return mp

    def _archive_combo(self, combo):
        combo.archived = True
        combo.save()

    # ------------------------------------------------------------------
    # model defaults
    # ------------------------------------------------------------------

    def test_combo_not_archived_by_default(self):
        """New combos have archived=False."""
        self._make_rated_plan(self.main, self.side, date(2026, 6, 1), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self.assertFalse(combo.archived)

    # ------------------------------------------------------------------
    # service: toggle_combo_archived
    # ------------------------------------------------------------------

    def test_toggle_archives_combo(self):
        from .services import toggle_combo_archived

        self._make_rated_plan(self.main, self.side, date(2026, 6, 2), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        toggle_combo_archived(combo)
        combo.refresh_from_db()
        self.assertTrue(combo.archived)

    def test_toggle_unarchives_combo(self):
        from .services import toggle_combo_archived

        self._make_rated_plan(self.main, self.side, date(2026, 6, 3), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        toggle_combo_archived(combo)
        combo.refresh_from_db()
        self.assertFalse(combo.archived)

    # ------------------------------------------------------------------
    # service: get_qualified_combos excludes archived by default
    # ------------------------------------------------------------------

    def test_get_qualified_combos_excludes_archived(self):
        from .services import get_qualified_combos

        self._make_rated_plan(self.main, self.side, date(2026, 6, 4), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        self.assertEqual(len(list(get_qualified_combos())), 0)

    def test_get_qualified_combos_includes_archived_when_asked(self):
        from .services import get_qualified_combos

        self._make_rated_plan(self.main, self.side, date(2026, 6, 5), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        self.assertEqual(len(list(get_qualified_combos(exclude_archived=False))), 1)

    # ------------------------------------------------------------------
    # service: suggest_top_combo excludes archived
    # ------------------------------------------------------------------

    def test_suggest_top_combo_excludes_archived(self):
        from .services import suggest_top_combo

        self._make_rated_plan(self.main, self.side, date(2025, 6, 1), 5, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        self.assertIsNone(suggest_top_combo(today=date(2026, 6, 1)))

    # ------------------------------------------------------------------
    # view: combo_toggle_archive
    # ------------------------------------------------------------------

    def test_toggle_archive_post_archives(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 6), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        response = self.client.post(
            reverse("meals:combo_toggle_archive", kwargs={"pk": combo.pk})
        )
        self.assertEqual(response.status_code, 302)
        combo.refresh_from_db()
        self.assertTrue(combo.archived)

    def test_toggle_archive_post_unarchives(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 7), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        response = self.client.post(
            reverse("meals:combo_toggle_archive", kwargs={"pk": combo.pk})
        )
        self.assertEqual(response.status_code, 302)
        combo.refresh_from_db()
        self.assertFalse(combo.archived)

    def test_toggle_archive_get_not_allowed(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 8), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        response = self.client.get(
            reverse("meals:combo_toggle_archive", kwargs={"pk": combo.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_toggle_archive_404_for_missing(self):
        response = self.client.post(
            reverse("meals:combo_toggle_archive", kwargs={"pk": 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_toggle_archive_requires_login(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 9), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self.client.logout()

        response = self.client.post(
            reverse("meals:combo_toggle_archive", kwargs={"pk": combo.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    # ------------------------------------------------------------------
    # view: combo_list hides archived by default
    # ------------------------------------------------------------------

    def test_combo_list_excludes_archived_by_default(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 10), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        response = self.client.get(reverse("meals:combo_list"))
        self.assertEqual(len(response.context["combos"]), 0)

    def test_combo_list_includes_archived_with_toggle(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 11), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        response = self.client.get(
            reverse("meals:combo_list"), {"include_archived": "1"}
        )
        self.assertEqual(len(response.context["combos"]), 1)
        self.assertTrue(response.context["include_archived"])

    def test_combo_list_archive_toggle_link(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 12), 4, True)

        response = self.client.get(reverse("meals:combo_list"))
        self.assertContains(response, "Include archived")
        self.assertNotContains(response, "Hide archived")

        response = self.client.get(
            reverse("meals:combo_list"), {"include_archived": "1"}
        )
        self.assertContains(response, "Hide archived")

    # ------------------------------------------------------------------
    # view: combo_detail still shows archived combos
    # ------------------------------------------------------------------

    def test_combo_detail_shows_archived_combo(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 13), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        response = self.client.get(
            reverse("meals:combo_detail", kwargs={"pk": combo.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Archived")
        self.assertContains(response, "Unarchive")

    def test_combo_detail_unarchived_shows_archive_button(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 14), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)

        response = self.client.get(
            reverse("meals:combo_detail", kwargs={"pk": combo.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Archived")
        self.assertContains(response, "Archive")

    # ------------------------------------------------------------------
    # combo picker excludes archived
    # ------------------------------------------------------------------

    def test_combo_picker_excludes_archived(self):
        self._make_rated_plan(self.main, self.side, date(2026, 6, 15), 4, True)
        combo = Combo.objects.get(main_recipe=self.main, side_recipe=self.side)
        self._archive_combo(combo)

        plan = MealPlan.objects.create(
            date=date(2026, 6, 20),
            created_by=self.user,
            status="DRAFT",
        )
        response = self.client.get(
            reverse("meals:meal_plan_edit", kwargs={"pk": plan.pk})
        )
        self.assertNotContains(response, "Choose from combos")
