from django.contrib.auth import get_user_model
from django.test import TestCase


class LogoutTests(TestCase):
    """Verify the Django 5 POST-only logout flow."""

    def setUp(self):
        """Create and authenticate a user."""
        self.user = get_user_model().objects.create_user(
            username='logout-user',
            password='test-password',
        )
        self.client.force_login(self.user)

    def test_navbar_submits_logout_with_csrf(self):
        """Render logout as a CSRF-protected POST form."""
        response = self.client.get('/', secure=True)

        self.assertContains(response, '<form method="post" action="/user/logout/">')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_logout_requires_post(self):
        """Keep GET harmless and end the session through POST."""
        get_response = self.client.get('/user/logout/', secure=True)

        self.assertEqual(get_response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

        post_response = self.client.post('/user/logout/', secure=True)

        self.assertRedirects(post_response, '/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)
