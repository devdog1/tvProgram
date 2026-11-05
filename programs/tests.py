from django.test import TestCase, Client
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from programs.models import Program, Category, Community, SourceCode, ShareOption
from programs.forms import ProgramForm


class ProgramFormValidationTests(TestCase):
    def test_valid_program_form(self):
        data = {
            "title": "Town Council Meeting",
            "date_recorded": "2025-01-15",
            "expiry_date": "2025-12-31",
            "producer": "Jane Doe",
            "length": "01:30:00",
            "category": "current affairs",
            "community": ["Brandon", "Virden"],
            "source_code": "b - Single Camera Edited",
            "share": ["Brandon", "South"],
            "filename": "meeting_20250115.mp4",
            "comments": "Recorded at council chambers.",
        }
        form = ProgramForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        program = form.save()
        self.assertEqual(program.title, "Town Council Meeting")
        self.assertEqual(program.community, "Brandon,Virden")
        self.assertEqual(program.share, "Brandon,South")

    def test_missing_required_fields(self):
        form = ProgramForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)
        self.assertIn("producer", form.errors)
        self.assertIn("date_recorded", form.errors)
        self.assertIn("length", form.errors)
        self.assertIn("filename", form.errors)

    def test_invalid_date_format(self):
        form = ProgramForm(data={
            "title": "Test",
            "date_recorded": "15-01-2025",
            "producer": "Prod",
            "length": "00:10:00",
            "filename": "test.mp4",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("date_recorded", form.errors)

    def test_invalid_length_format(self):
        form = ProgramForm(data={
            "title": "Test",
            "date_recorded": "2025-01-15",
            "producer": "Prod",
            "length": "90 mins",
            "filename": "test.mp4",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("length", form.errors)

    def test_invalid_filename_format(self):
        # Missing extension
        form1 = ProgramForm(data={
            "title": "Test",
            "date_recorded": "2025-01-15",
            "producer": "Prod",
            "length": "00:10:00",
            "filename": "invalidfilename",
        })
        self.assertFalse(form1.is_valid())
        self.assertIn("filename", form1.errors)

        # Forbidden characters in filename
        form2 = ProgramForm(data={
            "title": "Test",
            "date_recorded": "2025-01-15",
            "producer": "Prod",
            "length": "00:10:00",
            "filename": "test/invalid*.mp4",
        })
        self.assertFalse(form2.is_valid())
        self.assertIn("filename", form2.errors)

    def test_comments_length_limit(self):
        form = ProgramForm(data={
            "title": "Test",
            "date_recorded": "2025-01-15",
            "producer": "Prod",
            "length": "00:10:00",
            "filename": "test.mp4",
            "comments": "A" * 256,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("comments", form.errors)

    def test_disabled_options_not_in_choices_for_new_entry(self):
        cat = Category.objects.create(name="disabled_cat", display_name="Disabled Cat", is_enabled=False)
        form = ProgramForm()
        choice_keys = [c[0] for c in form.fields["category"].choices]
        self.assertNotIn("disabled_cat", choice_keys)


class ProgramViewAndPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create groups
        self.creator_group = Group.objects.create(name="Program Creators")
        ct_prog = ContentType.objects.get_for_model(Program)
        self.p_add_prog = Permission.objects.get(content_type=ct_prog, codename="add_program")
        self.p_view_prog = Permission.objects.get(content_type=ct_prog, codename="view_program")
        self.creator_group.permissions.add(self.p_add_prog, self.p_view_prog)

        self.editor_group = Group.objects.create(name="Program Editors")
        for model in [Category, Community, SourceCode, ShareOption, Program]:
            ct = ContentType.objects.get_for_model(model)
            for action in ["add", "change", "delete", "view"]:
                perm = Permission.objects.get(content_type=ct, codename=f"{action}_{model._meta.model_name}")
                self.editor_group.permissions.add(perm)

        # Users
        self.viewer_user = User.objects.create_user(username="viewer", password="password123")
        self.creator_user = User.objects.create_user(username="creator", password="password123")
        self.creator_user.groups.add(self.creator_group)
        self.editor_user = User.objects.create_user(username="editor", password="password123")
        self.editor_user.groups.add(self.editor_group)

        # Sample program
        self.sample_program = Program.objects.create(
            title="Initial Show",
            date_recorded="2025-01-10",
            producer="John",
            length="00:30:00",
            filename="show.mp4",
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("program_list"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))

    def test_authenticated_user_can_view_list(self):
        self.client.login(username="viewer", password="password123")
        response = self.client.get(reverse("program_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Initial Show")

    def test_creator_can_create_program(self):
        self.client.login(username="creator", password="password123")
        response = self.client.post(
            reverse("program_create"),
            {
                "title": "Created by Creator",
                "date_recorded": "2025-02-01",
                "producer": "Bob",
                "length": "00:45:00",
                "filename": "bob_show.mp4",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Program.objects.filter(title="Created by Creator").exists())

    def test_creator_cannot_edit_or_delete_program(self):
        self.client.login(username="creator", password="password123")
        edit_url = reverse("program_edit", args=[self.sample_program.id])
        res_edit = self.client.get(edit_url)
        self.assertEqual(res_edit.status_code, 403)

        del_url = reverse("program_delete", args=[self.sample_program.id])
        res_del = self.client.post(del_url)
        self.assertEqual(res_del.status_code, 403)

    def test_creator_cannot_access_options_management(self):
        self.client.login(username="creator", password="password123")
        response = self.client.get(reverse("options_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_editor_can_edit_and_delete_program(self):
        self.client.login(username="editor", password="password123")

        # Edit program
        edit_url = reverse("program_edit", args=[self.sample_program.id])
        res_edit = self.client.post(
            edit_url,
            {
                "title": "Initial Show (Edited)",
                "date_recorded": "2025-01-10",
                "producer": "John",
                "length": "00:30:00",
                "filename": "show.mp4",
            },
            follow=True,
        )
        self.assertEqual(res_edit.status_code, 200)
        self.sample_program.refresh_from_db()
        self.assertEqual(self.sample_program.title, "Initial Show (Edited)")

        # Delete program
        del_url = reverse("program_delete", args=[self.sample_program.id])
        res_del = self.client.post(del_url, follow=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(Program.objects.filter(id=self.sample_program.id).exists())

    def test_editor_can_manage_options_create_edit_toggle(self):
        self.client.login(username="editor", password="password123")

        # 1. Access dashboard
        res = self.client.get(reverse("options_dashboard"))
        self.assertEqual(res.status_code, 200)

        # 2. Create new Category
        res_create = self.client.post(
            reverse("option_create", args=["category"]),
            {"name": "wildlife", "display_name": "Wildlife & Nature", "is_enabled": True},
            follow=True,
        )
        self.assertEqual(res_create.status_code, 200)
        cat = Category.objects.get(name="wildlife")
        self.assertTrue(cat.is_enabled)

        # 3. Disable the category
        res_toggle = self.client.post(reverse("option_toggle", args=["category", cat.id]), follow=True)
        self.assertEqual(res_toggle.status_code, 200)
        cat.refresh_from_db()
        self.assertFalse(cat.is_enabled)

        # 4. Re-enable the category
        res_toggle2 = self.client.post(reverse("option_toggle", args=["category", cat.id]), follow=True)
        self.assertEqual(res_toggle2.status_code, 200)
        cat.refresh_from_db()
        self.assertTrue(cat.is_enabled)

        # 5. Edit the category
        res_edit = self.client.post(
            reverse("option_edit", args=["category", cat.id]),
            {"name": "wildlife", "display_name": "Wildlife and Outdoors", "is_enabled": True},
            follow=True,
        )
        self.assertEqual(res_edit.status_code, 200)
        cat.refresh_from_db()
        self.assertEqual(cat.display_name, "Wildlife and Outdoors")

    def test_program_creation_with_txt_attachment_download(self):
        self.client.login(username="creator", password="password123")
        res = self.client.post(
            reverse("program_create"),
            {
                "title": "Export Test",
                "date_recorded": "2025-03-01",
                "producer": "Alice",
                "length": "00:15:00",
                "filename": "export.mp4",
                "download_txt": "1",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/plain")
        self.assertIn("filename=\"export.txt\"", res["Content-Disposition"])
        content = res.content.decode("utf-8")
        self.assertIn("title: Export Test", content)
        self.assertIn("producer: Alice", content)
