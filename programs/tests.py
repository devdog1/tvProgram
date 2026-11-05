from django.test import TestCase, Client
from django.contrib.auth.models import User, Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from django.core import mail
from programs.models import (
    Program,
    Category,
    Community,
    SourceCode,
    ShareOption,
    Series,
    CustomField,
    CustomFieldValue,
    ProgramAttachment,
    ChangeLog,
    EventHook,
)
from programs.forms import ProgramForm


class WCGtvComprehensiveTests(TestCase):
    def setUp(self):
        # Create users
        self.creator_user = User.objects.create_user(username="creator", password="password123")
        self.other_user = User.objects.create_user(username="other", password="password123")
        self.editor_user = User.objects.create_user(username="editor", password="password123")
        self.admin_user = User.objects.create_superuser(username="admin", password="password123")

        # Set up creator permissions (can add_program, but NO change/delete permissions globally)
        p_add = Permission.objects.get(codename="add_program")
        self.creator_user.user_permissions.add(p_add)
        self.other_user.user_permissions.add(p_add)

        # Set up editor permissions (can add, change, delete, and change options)
        p_change = Permission.objects.get(codename="change_program")
        p_delete = Permission.objects.get(codename="delete_program")
        p_cat = Permission.objects.get(codename="change_category")
        self.editor_user.user_permissions.add(p_add, p_change, p_delete, p_cat)

        # Populate defaults
        Category.objects.get_or_create(name="arts/music", defaults={"display_name": "Arts/Music"})
        Community.objects.get_or_create(name="Brandon")
        Community.objects.get_or_create(name="Dauphin")
        SourceCode.objects.get_or_create(name="a - Single Camera/No Editing")
        ShareOption.objects.get_or_create(name="Brandon")

    # 1. Validation tests
    def test_program_form_validation(self):
        # Valid form data
        valid_data = {
            "title": "Local Concert",
            "date_recorded": "2025-05-10",
            "expiry_date": "2026-05-10",
            "producer": "Jane Doe",
            "length": "00:45:30",
            "category": "arts/music",
            "community": ["Brandon"],
            "share": ["Brandon"],
            "source_code": "a - Single Camera/No Editing",
            "filename": "concert.mp4",
            "comments": "Great audio",
        }
        form = ProgramForm(data=valid_data)
        self.assertTrue(form.is_valid(), form.errors)

        # Invalid length format
        bad_length_data = valid_data.copy()
        bad_length_data["length"] = "45:30"
        form = ProgramForm(data=bad_length_data)
        self.assertFalse(form.is_valid())
        self.assertIn("length", form.errors)

        # Invalid filename (no extension)
        bad_filename_data = valid_data.copy()
        bad_filename_data["filename"] = "concert_without_ext"
        form = ProgramForm(data=bad_filename_data)
        self.assertFalse(form.is_valid())
        self.assertIn("filename", form.errors)

        # Comments too long (> 255 chars)
        long_comment_data = valid_data.copy()
        long_comment_data["comments"] = "x" * 256
        form = ProgramForm(data=long_comment_data)
        self.assertFalse(form.is_valid())
        self.assertIn("comments", form.errors)

    # 2. Creator permission tests: can edit own program, but cannot delete it
    def test_creator_can_edit_own_program_but_cannot_delete(self):
        program = Program.objects.create(
            title="Creator Special",
            date_recorded="2025-01-01",
            producer="Creator Guy",
            length="01:00:00",
            filename="creator_prog.mp4",
            created_by=self.creator_user,
        )

        client = Client()
        client.login(username="creator", password="password123")

        # Creator can access edit page
        edit_url = reverse("program_edit", kwargs={"pk": program.pk})
        resp = client.get(edit_url)
        self.assertEqual(resp.status_code, 200)

        # Creator successfully updates their program
        post_resp = client.post(
            edit_url,
            {
                "title": "Creator Special Edited",
                "date_recorded": "2025-01-01",
                "producer": "Creator Guy",
                "length": "01:00:00",
                "filename": "creator_prog_v2.mp4",
            },
        )
        self.assertEqual(post_resp.status_code, 302)
        program.refresh_from_db()
        self.assertEqual(program.title, "Creator Special Edited")

        # Creator CANNOT delete their program (must return 403 PermissionDenied)
        del_url = reverse("program_delete", kwargs={"pk": program.pk})
        del_resp = client.post(del_url)
        self.assertEqual(del_resp.status_code, 403)
        self.assertTrue(Program.objects.filter(pk=program.pk).exists())

        # Other non-privileged user cannot edit
        client_other = Client()
        client_other.login(username="other", password="password123")
        resp_other = client_other.get(edit_url)
        self.assertEqual(resp_other.status_code, 403)

        # Editor user CAN delete
        client_editor = Client()
        client_editor.login(username="editor", password="password123")
        del_editor_resp = client_editor.post(del_url)
        self.assertEqual(del_editor_resp.status_code, 302)
        self.assertFalse(Program.objects.filter(pk=program.pk).exists())

    # 3. ChangeLog audit history tests
    def test_changelog_recorded_on_program_lifecycle(self):
        client = Client()
        client.login(username="creator", password="password123")

        # Create program via view
        client.post(
            reverse("program_create"),
            {
                "title": "Audit Test Program",
                "date_recorded": "2025-06-01",
                "producer": "Auditor",
                "length": "00:30:00",
                "filename": "audit.mp4",
            },
        )
        program = Program.objects.get(title="Audit Test Program")

        # Verify Created ChangeLog entry
        log_create = ChangeLog.objects.filter(object_id=str(program.id), action="Created").first()
        self.assertIsNotNone(log_create)
        self.assertEqual(log_create.user, self.creator_user)

        # Update program
        client.post(
            reverse("program_edit", kwargs={"pk": program.pk}),
            {
                "title": "Audit Test Program Updated",
                "date_recorded": "2025-06-01",
                "producer": "Auditor",
                "length": "00:35:00",
                "filename": "audit.mp4",
            },
        )
        log_update = ChangeLog.objects.filter(object_id=str(program.id), action="Updated").first()
        self.assertIsNotNone(log_update)

    # 4. Attachments tests
    def test_program_file_attachments(self):
        program = Program.objects.create(
            title="Attachment Program",
            date_recorded="2025-01-01",
            producer="Attacher",
            length="00:15:00",
            filename="attach_prog.mp4",
            created_by=self.creator_user,
        )

        client = Client()
        client.login(username="creator", password="password123")

        test_file = SimpleUploadedFile("cue_sheet.txt", b"Broadcast run order details...", content_type="text/plain")
        resp = client.post(
            reverse("program_attach_file", kwargs={"pk": program.pk}),
            {"file": test_file, "description": "Audio Cue Sheet"},
        )
        self.assertEqual(resp.status_code, 302)

        attachment = ProgramAttachment.objects.filter(program=program).first()
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.description, "Audio Cue Sheet")
        self.assertEqual(attachment.uploaded_by, self.creator_user)

    # 5. Custom Metadata Fields
    def test_custom_fields_creation_and_program_association(self):
        # Admin creates a custom field
        client_admin = Client()
        client_admin.login(username="admin", password="password123")

        client_admin.post(
            reverse("custom_field_create"),
            {
                "label": "Music License Code",
                "name": "music_license_code",
                "field_type": "text",
                "required": False,
                "is_active": True,
            },
        )
        cf = CustomField.objects.get(name="music_license_code")
        self.assertEqual(cf.label, "Music License Code")

        # Creator creates a program with this custom field
        client_creator = Client()
        client_creator.login(username="creator", password="password123")
        client_creator.post(
            reverse("program_create"),
            {
                "title": "Licensed Program",
                "date_recorded": "2025-02-01",
                "producer": "Music Prod",
                "length": "00:20:00",
                "filename": "music.mp4",
                "custom_field_music_license_code": "BMI-998877",
            },
        )
        p = Program.objects.get(title="Licensed Program")
        cf_val = CustomFieldValue.objects.get(program=p, custom_field=cf)
        self.assertEqual(cf_val.value, "BMI-998877")

    # 6. Episodic Series Linkage
    def test_episodic_programs_linked_to_series(self):
        series = Series.objects.create(
            title="Manitoba Outdoors",
            series_type="tv_series",
            created_by=self.creator_user,
        )

        program_ep1 = Program.objects.create(
            title="Fishing Lake Dauphin",
            series=series,
            season_number=1,
            episode_number=1,
            date_recorded="2025-03-01",
            producer="Outdoor Crew",
            length="00:28:30",
            filename="outdoors_s01e01.mp4",
            created_by=self.creator_user,
        )

        self.assertEqual(series.episodes.count(), 1)
        self.assertEqual(program_ep1.series.title, "Manitoba Outdoors")
        self.assertEqual(program_ep1.season_number, 1)
        self.assertEqual(program_ep1.episode_number, 1)

    # 7. Sign-off Validation Process
    def test_signoff_workflow(self):
        program = Program.objects.create(
            title="Needs Approval",
            date_recorded="2025-04-01",
            producer="Producer A",
            length="00:10:00",
            filename="draft.mp4",
            status="draft",
            created_by=self.creator_user,
        )

        # Creator submits program for review
        client_creator = Client()
        client_creator.login(username="creator", password="password123")
        client_creator.post(
            reverse("program_signoff", kwargs={"pk": program.pk}),
            {"action": "submit_for_review", "notes": "Ready for QC"},
        )
        program.refresh_from_db()
        self.assertEqual(program.status, "pending_review")

        # Creator CANNOT self-approve (needs signoff permission / editor role)
        creator_approve_resp = client_creator.post(
            reverse("program_signoff", kwargs={"pk": program.pk}),
            {"action": "approve", "notes": "Self approving"},
        )
        self.assertEqual(creator_approve_resp.status_code, 403)

        # Editor approves and signs off
        client_editor = Client()
        client_editor.login(username="editor", password="password123")
        editor_approve_resp = client_editor.post(
            reverse("program_signoff", kwargs={"pk": program.pk}),
            {"action": "approve", "notes": "Approved for broadcast"},
        )
        self.assertEqual(editor_approve_resp.status_code, 302)
        program.refresh_from_db()
        self.assertEqual(program.status, "signed_off")
        self.assertEqual(program.signed_off_by, self.editor_user)
        self.assertIsNotNone(program.signed_off_at)

    # 8. Event Hook Manager Tests
    def test_event_hook_creation_and_email_trigger_on_program_added(self):
        # Create an event hook to trigger email on program_created
        hook = EventHook.objects.create(
            name="Notify on Program Added",
            event_type="program_created",
            action_type="email",
            is_active=True,
            recipient_emails="ops@wcgtv.local, manager@wcgtv.local",
            email_subject="New Program: {title}",
            email_body="Hello, program '{title}' was submitted by {user}.",
            created_by=self.admin_user,
        )

        client_creator = Client()
        client_creator.login(username="creator", password="password123")

        # Clear test mailbox
        mail.outbox.clear()

        # Submit program
        resp = client_creator.post(
            reverse("program_create"),
            {
                "title": "Evening News Special",
                "date_recorded": "2025-07-01",
                "producer": "News Desk",
                "length": "00:30:00",
                "filename": "news_special.mp4",
            },
        )
        self.assertEqual(resp.status_code, 302)

        # Verify email was dispatched to outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, "New Program: Evening News Special")
        self.assertIn("Evening News Special", sent_email.body)
        self.assertIn("creator", sent_email.body)
        self.assertIn("ops@wcgtv.local", sent_email.to)
        self.assertIn("manager@wcgtv.local", sent_email.to)

        # Verify hook last_triggered_at was updated
        hook.refresh_from_db()
        self.assertIsNotNone(hook.last_triggered_at)

    # 9. Bulk CSV Import Tests
    def test_bulk_csv_import_success(self):
        client = Client()
        client.login(username="creator", password="password123")

        csv_data = (
            'id,created,title,dateRecorded,expiryDate,producer,length,category,community,sourceCode,share,filename,comments\n'
            '100,"2015-03-10 16:47:28",Soccer Match 1,2015-02-02,,fred,01:02:03,sports,,,,asfhnafuopsgdhosgdu90sgd.mp4,\n'
            '101,"2015-03-10 16:55:48",Soccer Match 2,2015-03-11,,fred,01:02:03,sports,,,,asfhnafuopsgdhosgdu90sgd.mp4,"Imported comment"'
        )

        resp = client.post(
            reverse("program_bulk_import"),
            {
                "csv_text": csv_data,
                "preserve_ids": True,
                "skip_errors": True,
            },
        )
        self.assertEqual(resp.status_code, 200)

        p1 = Program.objects.get(id=100)
        self.assertEqual(p1.title, "Soccer Match 1")
        self.assertEqual(str(p1.date_recorded), "2015-02-02")
        self.assertEqual(p1.producer, "fred")
        self.assertEqual(p1.length, "01:02:03")
        self.assertEqual(p1.category, "sports")
        self.assertEqual(p1.filename, "asfhnafuopsgdhosgdu90sgd.mp4")

        p2 = Program.objects.get(id=101)
        self.assertEqual(p2.title, "Soccer Match 2")
        self.assertEqual(p2.comments, "Imported comment")

        # Verify ChangeLog was written for the import
        log1 = ChangeLog.objects.filter(object_id="100", action="Created").first()
        self.assertIsNotNone(log1)

    def test_bulk_csv_import_invalid_row_handling(self):
        client = Client()
        client.login(username="creator", password="password123")

        bad_csv_data = (
            'id,created,title,dateRecorded,expiryDate,producer,length,category,community,sourceCode,share,filename,comments\n'
            ',,Invalid Time Program,2025-01-01,,producer1,99:99,sports,,,,valid.mp4,\n'
            ',,Valid Bulk Program,2025-01-01,,producer2,00:30:00,sports,,,,valid.mp4,'
        )

        resp = client.post(
            reverse("program_bulk_import"),
            {
                "csv_text": bad_csv_data,
                "skip_errors": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        # 1 valid program saved, 1 skipped due to invalid time
        self.assertTrue(Program.objects.filter(title="Valid Bulk Program").exists())
        self.assertFalse(Program.objects.filter(title="Invalid Time Program").exists())
        self.assertIn("Invalid length '99:99'", resp.context["results"]["errors"][0])

    # 10. Large dataset pagination & unauthenticated layout test
    def test_unauthenticated_user_sees_no_menu(self):
        client = Client()
        # GET login page
        resp = client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        # Ensure sidebar menu and links are NOT rendered
        self.assertNotIn("id=\"sidebar-wrapper\"", content)
        self.assertNotIn("Dashboard", content)
        self.assertNotIn("Sign-off Queue", content)
        self.assertNotIn("Bulk CSV Import", content)
        # Ensure login form is rendered
        self.assertIn("WCGtv Metadata Tool", content)
        self.assertIn("Sign In", content)

    def test_program_filtering_options(self):
        # Create varied programs
        Program.objects.create(
            title="Brandon Football Final",
            date_recorded="2025-05-15",
            producer="Sports Team",
            length="01:30:00",
            category="sports",
            community="Brandon",
            source_code="a - Single Camera/No Editing",
            filename="football.mp4",
            status="signed_off",
            created_by=self.creator_user,
        )
        Program.objects.create(
            title="Music Showcase",
            date_recorded="2025-06-20",
            producer="Music Team",
            length="00:45:00",
            category="arts/music",
            community="Dauphin",
            source_code="a - Single Camera/No Editing",
            filename="showcase.mp4",
            status="draft",
            created_by=self.creator_user,
        )

        client = Client()
        client.login(username="creator", password="password123")

        # 1. Keyword search 'Football'
        resp_q = client.get(reverse("program_list") + "?q=Football")
        self.assertEqual(resp_q.status_code, 200)
        self.assertEqual(len(resp_q.context["programs"]), 1)
        self.assertEqual(resp_q.context["programs"][0].title, "Brandon Football Final")

        # 2. Status filter 'draft'
        resp_status = client.get(reverse("program_list") + "?status=draft")
        self.assertEqual(resp_status.status_code, 200)
        self.assertTrue(all(p.status == "draft" for p in resp_status.context["programs"]))

        # 3. Category filter 'arts/music'
        resp_cat = client.get(reverse("program_list") + "?category=arts/music")
        self.assertEqual(resp_cat.status_code, 200)
        self.assertTrue(all(p.category == "arts/music" for p in resp_cat.context["programs"]))

        # 4. Community filter 'Brandon'
        resp_comm = client.get(reverse("program_list") + "?community=Brandon")
        self.assertEqual(resp_comm.status_code, 200)
        self.assertEqual(resp_comm.context["programs"][0].title, "Brandon Football Final")

        # 5. Date recorded range
        resp_date = client.get(reverse("program_list") + "?date_from=2025-06-01&date_to=2025-06-30")
        self.assertEqual(resp_date.status_code, 200)
        self.assertEqual(len(resp_date.context["programs"]), 1)
        self.assertEqual(resp_date.context["programs"][0].title, "Music Showcase")

    def test_large_dataset_pagination(self):
        # Create 120 programs efficiently with bulk_create
        progs = [
            Program(
                title=f"Bulk Scale Program {i}",
                date_recorded="2025-01-01",
                producer="Scale Producer",
                length="00:30:00",
                filename=f"scale_{i}.mp4",
                category="sports",
                created_by=self.creator_user,
            )
            for i in range(120)
        ]
        Program.objects.bulk_create(progs)

        client = Client()
        client.login(username="creator", password="password123")

        # Request page 1 with 50 per page
        resp = client.get(reverse("program_list") + "?per_page=50&page=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["programs"]), 50)
        self.assertEqual(resp.context["total_count"], 120)

        # Request page 3 (remaining 20)
        resp3 = client.get(reverse("program_list") + "?per_page=50&page=3")
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(len(resp3.context["programs"]), 20)
