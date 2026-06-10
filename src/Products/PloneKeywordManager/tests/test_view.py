from plone import api
from Products.PloneKeywordManager.tests.base import PKMTestCase
from Products.PloneKeywordManager.tool import _attr_from_accessor
from Products.statusmessages.interfaces import IStatusMessage
from zope.component import getMultiAdapter


class ViewCallTestCase(PKMTestCase):
    """Exercise the prefs_keywords_view __call__ request-handling flow."""

    def setUp(self):
        super().setUp()
        self.content = api.content.create(
            container=self.portal, type="Document", id="doc"
        )
        self.content.setSubject(["alpha", "beta"])
        self.content.reindexObject()
        self.request.form.clear()

    def _view(self):
        return getMultiAdapter((self.portal, self.request), name="prefs_keywords_view")

    def _messages(self):
        return " ".join(str(m.message) for m in IStatusMessage(self.request).show())

    def test_no_button_renders_template(self):
        self.assertTrue(self._view()())

    def test_merge_without_keywords_is_rejected(self):
        self.request.form["form.button.Merge"] = "1"
        self._view()()
        self.assertIn("at least one keyword", self._messages())

    def test_merge_with_invalid_field_is_rejected(self):
        self.request.form["form.button.Merge"] = "1"
        self.request.form["keywords"] = ["alpha"]
        self.request.form["field"] = "NotAnIndex"
        self._view()()
        self.assertIn("valid keyword field", self._messages())

    def test_merge_without_changeto_is_rejected(self):
        self.request.form["form.button.Merge"] = "1"
        self.request.form["keywords"] = ["alpha"]
        self.request.form["field"] = "Subject"
        self._view()()
        self.assertIn("new term", self._messages())

    def test_merge_changes_keywords(self):
        self.request.form["form.button.Merge"] = "1"
        self.request.form["keywords"] = ["alpha"]
        self.request.form["field"] = "Subject"
        self.request.form["changeto"] = "gamma"
        self._view()()
        self.assertEqual(sorted(self.content.Subject()), ["beta", "gamma"])

    def test_delete_removes_keywords(self):
        self.request.form["form.button.Delete"] = "1"
        self.request.form["keywords"] = ["beta"]
        self.request.form["field"] = "Subject"
        self._view()()
        self.assertEqual(sorted(self.content.Subject()), ["alpha"])


class AccessorHelperTestCase(PKMTestCase):
    """Regression tests for the accessor-name helper (the lstrip bug fix)."""

    def test_camelcase_accessor(self):
        self.assertEqual(_attr_from_accessor("getSubject"), "subject")

    def test_snake_case_accessor(self):
        # Previously ``"get_text".lstrip("get_")`` returned "xt".
        self.assertEqual(_attr_from_accessor("get_text"), "text")

    def test_plain_field_name(self):
        self.assertEqual(_attr_from_accessor("Subject"), "subject")

    def test_camelcase_accessor_with_following_t(self):
        self.assertEqual(_attr_from_accessor("getText"), "text")
