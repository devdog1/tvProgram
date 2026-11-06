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
    APIKey,
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
                "target_element": "program",
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
        # Give creator the can_bulk_import permission for this test
        p_bulk = Permission.objects.get(codename="can_bulk_import")
        self.creator_user.user_permissions.add(p_bulk)
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
        p_bulk = Permission.objects.get(codename="can_bulk_import")
        self.creator_user.user_permissions.add(p_bulk)
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

    # 11. Change Log displayed on Program Detail page test
    def test_changelog_displayed_on_program_detail(self):
        program = Program.objects.create(
            title="Detailed Program With History",
            date_recorded="2025-05-01",
            producer="Jane Producer",
            length="00:25:00",
            filename="detailed_history.mp4",
            created_by=self.creator_user,
        )

        # Generate some ChangeLog entries for this program
        ChangeLog.objects.create(
            user=self.creator_user,
            user_display="creator",
            action="Created",
            object_type="Program",
            object_id=str(program.id),
            object_repr=str(program),
            details='{"title": "Detailed Program With History"}',
        )
        ChangeLog.objects.create(
            user=self.editor_user,
            user_display="editor",
            action="Updated",
            object_type="Program",
            object_id=str(program.id),
            object_repr=str(program),
            details='{"fields_changed": ["producer"]}',
        )

        client = Client()
        client.login(username="creator", password="password123")

        resp = client.get(reverse("program_detail", kwargs={"pk": program.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("change_logs", resp.context)
        self.assertEqual(len(resp.context["change_logs"]), 2)

        content = resp.content.decode("utf-8")
        self.assertIn(f"Change Log for Program #{program.id}", content)
        self.assertIn("Detailed Program With History", content)
        self.assertIn("fields_changed", content)
        self.assertIn("editor", content)

    # 12. Options creation and URL reversal tests
    def test_options_create_and_reverse_url(self):
        client = Client()
        client.login(username="editor", password="password123")

        # GET options/category/new/
        resp = client.get(reverse("option_create", kwargs={"model_name": "category"}))
        self.assertEqual(resp.status_code, 200)

        # POST new category
        post_resp = client.post(
            reverse("option_create", kwargs={"model_name": "category"}),
            {"name": "science", "display_name": "Science & Tech", "is_enabled": True},
        )
        self.assertEqual(post_resp.status_code, 302)
        self.assertTrue(Category.objects.filter(name="science").exists())

        # Test both manage_options and options_dashboard reversibility
        self.assertEqual(reverse("manage_options"), "/options/")
        self.assertEqual(reverse("options_dashboard"), "/options/")

    # 13. Dedicated Bulk Import permission tests
    def test_bulk_import_permission_required(self):
        client = Client()
        client.login(username="creator", password="password123")

        # Creator does NOT have can_bulk_import permission initially -> should return 403
        resp_denied = client.get(reverse("program_bulk_import"))
        self.assertEqual(resp_denied.status_code, 403)

        # Grant can_bulk_import permission to creator
        p_bulk = Permission.objects.get(codename="can_bulk_import")
        self.creator_user.user_permissions.add(p_bulk)
        self.creator_user = User.objects.get(pk=self.creator_user.pk)

        # Now creator can access
        resp_allowed = client.get(reverse("program_bulk_import"))
        self.assertEqual(resp_allowed.status_code, 200)

    # 14. Custom Fields with Target Element, File Upload, and Enum
    def test_custom_fields_target_element_and_types(self):
        # 1. Create Enum Custom Field for Program
        enum_field = CustomField.objects.create(
            target_element="program",
            name="broadcast_res",
            label="Broadcast Resolution",
            field_type="enum",
            choices="720p, 1080p, 4K UHD",
            is_active=True,
        )
        self.assertEqual(enum_field.choices_list, ["720p", "1080p", "4K UHD"])

        # 2. Create File Custom Field for Series
        file_field = CustomField.objects.create(
            target_element="series",
            name="series_bible",
            label="Series Production Bible",
            field_type="file",
            is_active=True,
        )

        client = Client()
        client.login(username="creator", password="password123")

        # Submit Program with Enum value
        resp_prog = client.post(
            reverse("program_create"),
            {
                "title": "UHD Nature Doc",
                "date_recorded": "2025-08-01",
                "producer": "Nature Unit",
                "length": "00:50:00",
                "filename": "nature_uhd.mp4",
                "custom_field_broadcast_res": "4K UHD",
            },
        )
        self.assertEqual(resp_prog.status_code, 302)
        prog = Program.objects.get(title="UHD Nature Doc")
        cfv_prog = CustomFieldValue.objects.get(program=prog, custom_field=enum_field)
        self.assertEqual(cfv_prog.value, "4K UHD")

        # Submit Series with File Upload
        series_file = SimpleUploadedFile("bible.pdf", b"%PDF-1.4 series bible content...", content_type="application/pdf")
        resp_series = client.post(
            reverse("series_create"),
            {
                "title": "Prairie Chronicles",
                "series_type": "tv_series",
                "description": "Historical drama",
                "custom_field_series_bible": series_file,
            },
        )
        self.assertEqual(resp_series.status_code, 302)
        series = Series.objects.get(title="Prairie Chronicles")
        cfv_series = CustomFieldValue.objects.get(series=series, custom_field=file_field)
        self.assertTrue(bool(cfv_series.file_upload))
        self.assertIn("bible", cfv_series.file_upload.name)

    # 19. Series Created Event Hook and Dispatch History View Tests
    def test_series_created_event_hook_and_dispatch_history_view(self):
        # 1. Create a Series Created Event Hook
        hook = EventHook.objects.create(
            name="Notify on Series Added",
            event_type="series_created",
            action_type="email",
            is_active=True,
            recipient_emails="series-lead@wcgtv.local",
            email_subject="Series Registered: {title}",
            email_body="Series {title} was registered.",
            created_by=self.admin_user,
        )

        client_creator = Client()
        client_creator.login(username="creator", password="password123")
        mail.outbox.clear()

        # Create series
        resp = client_creator.post(
            reverse("series_create"),
            {
                "title": "Westman Wildlife",
                "series_type": "tv_series",
                "description": "Nature docu-series",
            },
        )
        self.assertEqual(resp.status_code, 302)

        # Confirm email was dispatched to outbox
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.subject, "Series Registered: Westman Wildlife")
        self.assertIn("series-lead@wcgtv.local", sent.to)

        # Confirm ChangeLog recorded the dispatched email action
        series = Series.objects.get(title="Westman Wildlife")
        dispatch_log = ChangeLog.objects.filter(action="Dispatched Email", object_id=str(series.id)).first()
        self.assertIsNotNone(dispatch_log)

        # 2. Test global Change Log admin restriction
        # Creator cannot access global changelog -> 403
        resp_creator_cl = client_creator.get(reverse("changelog_list"))
        self.assertEqual(resp_creator_cl.status_code, 403)

        # Admin CAN access global changelog -> 200
        client_admin = Client()
        client_admin.login(username="admin", password="password123")
        resp_admin_cl = client_admin.get(reverse("changelog_list"))
        self.assertEqual(resp_admin_cl.status_code, 200)

        # Allowed user CAN view change log on series detail page
        resp_series_detail = client_creator.get(reverse("series_detail", kwargs={"pk": series.pk}))
        self.assertEqual(resp_series_detail.status_code, 200)
        self.assertIn("change_logs", resp_series_detail.context)
        self.assertTrue(len(resp_series_detail.context["change_logs"]) >= 1)

        # 3. Test Event Hook Actions view (admin only)
        # Creator cannot access -> 403
        resp_creator_actions = client_creator.get(reverse("event_hook_history"))
        self.assertEqual(resp_creator_actions.status_code, 403)

        # Admin CAN access -> 200 and sees dispatched email
        resp_admin_actions = client_admin.get(reverse("event_hook_history"))
        self.assertEqual(resp_admin_actions.status_code, 200)
        self.assertIn("logs", resp_admin_actions.context)
        self.assertTrue(len(resp_admin_actions.context["logs"]) >= 1)

    # 20. Dashboard Scoping Tests based on User Access
    def test_dashboard_scoping_by_user_access(self):
        group_sports = Group.objects.create(name="Sports Producers")
        group_news = Group.objects.create(name="News Producers")

        user_sports = User.objects.create_user(username="sports_guy", password="password123")
        user_sports.groups.add(group_sports)

        user_news = User.objects.create_user(username="news_gal", password="password123")
        user_news.groups.add(group_news)

        # Create programs
        Program.objects.create(
            title="Sports Prog 1",
            date_recorded="2025-01-01",
            producer="P",
            length="00:10:00",
            filename="sp1.mp4",
            owner_group=group_sports,
            status="signed_off",
        )
        Program.objects.create(
            title="News Prog 1",
            date_recorded="2025-01-01",
            producer="P",
            length="00:10:00",
            filename="np1.mp4",
            owner_group=group_news,
            status="signed_off",
        )

        # Create series
        Series.objects.create(title="Sports Series 1", owner_group=group_sports)
        Series.objects.create(title="News Series 1", owner_group=group_news)

        # 1. Sports user visits dashboard: sees 1 program, 1 series
        client = Client()
        client.login(username="sports_guy", password="password123")
        resp_sports = client.get(reverse("dashboard"))
        self.assertEqual(resp_sports.status_code, 200)
        self.assertEqual(resp_sports.context["programs_count"], 1)
        self.assertEqual(resp_sports.context["series_count"], 1)
        # Regular user does not see change log or Swagger link in HTML
        content_sports = resp_sports.content.decode("utf-8")
        self.assertNotIn("REST API (Swagger)", content_sports)
        self.assertNotIn("API Keys", content_sports)
        self.assertNotIn("Recent Change Activity", content_sports)

        # 2. Admin visits dashboard: sees all 2 programs, 2 series, and admin links
        client_admin = Client()
        client_admin.login(username="admin", password="password123")
        resp_admin = client_admin.get(reverse("dashboard"))
        self.assertEqual(resp_admin.status_code, 200)
        self.assertTrue(resp_admin.context["programs_count"] >= 2)
        self.assertTrue(resp_admin.context["series_count"] >= 2)
        content_admin = resp_admin.content.decode("utf-8")
        self.assertIn("REST API (Swagger)", content_admin)
        self.assertIn("API Keys", content_admin)
        self.assertIn("Change Log", content_admin)

    # 15. User Group Ownership, Edit Permissions, and Draft Reset Tests
    def test_owner_group_permissions_and_edit_draft_reset(self):
        sports_group = Group.objects.create(name="Sports Production Group")
        news_group = Group.objects.create(name="News Production Group")

        # Put creator in sports_group, other in news_group
        self.creator_user.groups.add(sports_group)
        self.other_user.groups.add(news_group)

        # Create program owned by sports_group, signed off
        prog = Program.objects.create(
            title="Westman Volleyball Championship",
            date_recorded="2025-04-10",
            producer="Sports Group Lead",
            length="01:15:00",
            filename="volleyball.mp4",
            owner_group=sports_group,
            status="signed_off",
            signed_off_by=self.editor_user,
        )

        # Create user3 also in sports_group (not original author, but group member)
        user3 = User.objects.create_user(username="sports_colleague", password="password123")
        user3.groups.add(sports_group)

        client_user3 = Client()
        client_user3.login(username="sports_colleague", password="password123")

        # user3 can edit the program because they belong to the owner_group!
        edit_url = reverse("program_edit", kwargs={"pk": prog.pk})
        resp = client_user3.get(edit_url)
        self.assertEqual(resp.status_code, 200)

        # Submit an edit as user3
        post_resp = client_user3.post(
            edit_url,
            {
                "title": "Westman Volleyball Championship Final Cut",
                "owner_group": sports_group.id,
                "date_recorded": "2025-04-10",
                "producer": "Sports Group Lead",
                "length": "01:15:00",
                "filename": "volleyball_final.mp4",
            },
        )
        self.assertEqual(post_resp.status_code, 302)

        # Confirm program status was moved back to draft state, requiring redo of sign-off
        prog.refresh_from_db()
        self.assertEqual(prog.title, "Westman Volleyball Championship Final Cut")
        self.assertEqual(prog.status, "draft")
        self.assertIsNone(prog.signed_off_by)
        self.assertIsNone(prog.signed_off_at)
        self.assertIn("Reset to draft on edit", prog.sign_off_notes)

        # Member of news_group CANNOT edit sports_group program
        client_other = Client()
        client_other.login(username="other", password="password123")
        resp_forbidden = client_other.get(edit_url)
        self.assertEqual(resp_forbidden.status_code, 403)

    # 16. Default filtering by owner group vs view_all_programs and view_all_series
    def test_default_group_filtering_and_view_all_permissions(self):
        group_a = Group.objects.create(name="Station Alpha")
        group_b = Group.objects.create(name="Station Beta")

        user_alpha = User.objects.create_user(username="alpha_user", password="password123")
        user_alpha.groups.add(group_a)

        user_beta = User.objects.create_user(username="beta_user", password="password123")
        user_beta.groups.add(group_b)

        # Programs & Series for Alpha
        series_a = Series.objects.create(title="Alpha Series", owner_group=group_a)
        prog_a = Program.objects.create(
            title="Alpha Morning",
            date_recorded="2025-01-01",
            producer="A",
            length="00:30:00",
            filename="a.mp4",
            owner_group=group_a,
            series=series_a,
        )

        # Programs & Series for Beta
        series_b = Series.objects.create(title="Beta Series", owner_group=group_b)
        prog_b = Program.objects.create(
            title="Beta Evening",
            date_recorded="2025-01-01",
            producer="B",
            length="00:30:00",
            filename="b.mp4",
            owner_group=group_b,
            series=series_b,
        )

        client_alpha = Client()
        client_alpha.login(username="alpha_user", password="password123")

        # By default, user_alpha only sees group_a programs in program_list
        resp_progs = client_alpha.get(reverse("program_list"))
        prog_titles = [p.title for p in resp_progs.context["programs"]]
        self.assertIn("Alpha Morning", prog_titles)
        self.assertNotIn("Beta Evening", prog_titles)

        # By default, user_alpha only sees group_a series in series_list
        resp_series = client_alpha.get(reverse("series_list"))
        series_titles = [s.title for s in resp_series.context["series_list"]]
        self.assertIn("Alpha Series", series_titles)
        self.assertNotIn("Beta Series", series_titles)

        # When adding a program, the series selector only shows series visible to user_alpha (Alpha Series only)
        p_add = Permission.objects.get(codename="add_program")
        user_alpha.user_permissions.add(p_add)
        user_alpha = User.objects.get(pk=user_alpha.pk)

        resp_create = client_alpha.get(reverse("program_create"))
        series_field_qs = resp_create.context["form"].fields["series"].queryset
        self.assertIn(series_a, series_field_qs)
        self.assertNotIn(series_b, series_field_qs)

        # Grant user_alpha view_all_programs & view_all_series permissions
        p_all_p = Permission.objects.get(codename="view_all_programs")
        p_all_s = Permission.objects.get(codename="view_all_series")
        user_alpha.user_permissions.add(p_all_p, p_all_s)
        user_alpha = User.objects.get(pk=user_alpha.pk)

        # Now user_alpha sees all programs and all series
        resp_progs_all = client_alpha.get(reverse("program_list"))
        all_prog_titles = [p.title for p in resp_progs_all.context["programs"]]
        self.assertIn("Alpha Morning", all_prog_titles)
        self.assertIn("Beta Evening", all_prog_titles)

        resp_series_all = client_alpha.get(reverse("series_list"))
        all_series_titles = [s.title for s in resp_series_all.context["series_list"]]
        self.assertIn("Alpha Series", all_series_titles)
        self.assertIn("Beta Series", all_series_titles)

        # And series selector now includes both series
        resp_create_all = client_alpha.get(reverse("program_create"))
        series_field_qs_all = resp_create_all.context["form"].fields["series"].queryset
        self.assertIn(series_a, series_field_qs_all)
        self.assertIn(series_b, series_field_qs_all)

    def test_smtp_relay_settings_and_envelope_from(self):
        """
        Verify SMTP relay settings configuration and envelope sender (Return-Path) handling.
        """
        from .models import SMTPSettings
        from .services import send_wcgtv_email
        from django.core import mail

        SMTPSettings.objects.all().delete()
        smtp_cfg = SMTPSettings.objects.create(
            host="postfix.example.internal",
            port=25,
            from_address="wcgtv-noreply@wcgtv.org",
            envelope_from="postfix-bounces@wcgtv.org",
            is_active=True,
        )

        self.assertEqual(smtp_cfg.get_envelope_from(), "postfix-bounces@wcgtv.org")

        mail.outbox.clear()
        send_wcgtv_email("Alert Subject", "Alert Body", ["test-dest@wcgtv.org"])

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.from_email, "wcgtv-noreply@wcgtv.org")
        self.assertEqual(sent.extra_headers.get("Return-Path"), "postfix-bounces@wcgtv.org")
        self.assertEqual(sent.extra_headers.get("Sender"), "postfix-bounces@wcgtv.org")

        # Test admin settings view
        self.client.login(username="admin", password="password123")
        resp = self.client.get(reverse("smtp_settings"))
        self.assertEqual(resp.status_code, 200)

        # Update settings via post
        post_data = {
            "host": "relay.postfix.lan",
            "port": 587,
            "username": "smtpuser",
            "password": "secretpassword",
            "use_tls": True,
            "use_ssl": False,
            "timeout": 15,
            "from_address": "news@wcgtv.ca",
            "envelope_from": "bounces@wcgtv.ca",
            "is_active": True,
        }
        post_resp = self.client.post(reverse("smtp_settings"), post_data)
        self.assertRedirects(post_resp, reverse("smtp_settings"))

        smtp_cfg.refresh_from_db()
        self.assertEqual(smtp_cfg.host, "relay.postfix.lan")
        self.assertEqual(smtp_cfg.from_address, "news@wcgtv.ca")
        self.assertEqual(smtp_cfg.envelope_from, "bounces@wcgtv.ca")

    def test_signoff_queue_user_group_and_own_filtering(self):
        """
        Verify Sign-off Validation Queue defaults to user's own items and owner group items,
        unless user has view_all permissions.
        """
        group_news = Group.objects.create(name="News Group")
        group_sports = Group.objects.create(name="Sports Group")

        user_reporter = User.objects.create_user(username="reporter_user", password="password123")
        user_reporter.groups.add(group_news)

        # Items for News Group (pending review)
        prog_news = Program.objects.create(
            title="News at Noon",
            date_recorded="2025-02-01",
            producer="NewsTeam",
            length="00:30:00",
            filename="news.mp4",
            status="pending_review",
            owner_group=group_news,
        )
        series_news = Series.objects.create(
            title="Daily News Series",
            status="pending_review",
            owner_group=group_news,
        )

        # Items for Sports Group (pending review)
        prog_sports = Program.objects.create(
            title="Sports Roundup",
            date_recorded="2025-02-01",
            producer="SportsTeam",
            length="00:30:00",
            filename="sports.mp4",
            status="pending_review",
            owner_group=group_sports,
        )
        series_sports = Series.objects.create(
            title="Weekly Sports Highlights",
            status="pending_review",
            owner_group=group_sports,
        )

        client_reporter = Client()
        client_reporter.login(username="reporter_user", password="password123")

        # By default, reporter only sees News Group items in signoff queue
        resp_q = client_reporter.get(reverse("signoff_queue"))
        self.assertEqual(resp_q.status_code, 200)
        q_progs = [p.title for p in resp_q.context["pending_programs"]]
        q_series = [s.title for s in resp_q.context["pending_series"]]

        self.assertIn("News at Noon", q_progs)
        self.assertNotIn("Sports Roundup", q_progs)
        self.assertIn("Daily News Series", q_series)
        self.assertNotIn("Weekly Sports Highlights", q_series)

        # Add view_all permissions to reporter
        p_all_p = Permission.objects.get(codename="view_all_programs")
        p_all_s = Permission.objects.get(codename="view_all_series")
        user_reporter.user_permissions.add(p_all_p, p_all_s)
        user_reporter = User.objects.get(pk=user_reporter.pk)

        # Now reporter sees both news and sports items
        resp_q_all = client_reporter.get(reverse("signoff_queue"))
        all_q_progs = [p.title for p in resp_q_all.context["pending_programs"]]
        all_q_series = [s.title for s in resp_q_all.context["pending_series"]]

        self.assertIn("News at Noon", all_q_progs)
        self.assertIn("Sports Roundup", all_q_progs)
        self.assertIn("Daily News Series", all_q_series)
        self.assertIn("Weekly Sports Highlights", all_q_series)

    # 17. REST API Authentication & Approved Data Filtering Tests
    def test_api_key_authentication_and_approved_data_filtering(self):
        """
        Verify that REST API:
        1. Authenticates via X-API-Key and Authorization headers.
        2. By default only returns approved/signed-off programs to external systems.
        3. Excludes unapproved/pending approval data unless include_pending=true or status specified.
        4. Swagger UI and OpenAPI schema endpoints are functional.
        """
        # Create programs in various states
        prog_approved = Program.objects.create(
            title="Approved Ingest Program",
            date_recorded="2025-05-01",
            producer="Broadcast Team",
            length="00:30:00",
            filename="approved.mp4",
            status="signed_off",
            created_by=self.creator_user,
        )
        prog_pending = Program.objects.create(
            title="Unapproved Pending Review Program",
            date_recorded="2025-05-02",
            producer="Broadcast Team",
            length="00:30:00",
            filename="pending.mp4",
            status="pending_review",
            created_by=self.creator_user,
        )
        prog_draft = Program.objects.create(
            title="Unapproved Draft Program",
            date_recorded="2025-05-03",
            producer="Broadcast Team",
            length="00:30:00",
            filename="draft.mp4",
            status="draft",
            created_by=self.creator_user,
        )

        # Generate API key for creator
        api_key_obj = APIKey.generate_key(user=self.creator_user, name="Ingest Bot")

        client = Client()

        # Unauthenticated request to /api/v1/programs/ should fail 401 or 403
        resp_unauth = client.get("/api/v1/programs/")
        self.assertEqual(resp_unauth.status_code, 403)

        # Authenticate via X-API-Key header
        resp_x_api = client.get("/api/v1/programs/", HTTP_X_API_KEY=api_key_obj.key)
        self.assertEqual(resp_x_api.status_code, 200)
        data = resp_x_api.json()

        # Default query MUST only return signed-off / approved programs!
        returned_titles = [item["title"] for item in data["results"]]
        self.assertIn("Approved Ingest Program", returned_titles)
        self.assertNotIn("Unapproved Pending Review Program", returned_titles)
        self.assertNotIn("Unapproved Draft Program", returned_titles)

        # Authenticate via Authorization: Api-Key header
        resp_auth_header = client.get(
            "/api/v1/programs/",
            HTTP_AUTHORIZATION=f"Api-Key {api_key_obj.key}",
        )
        self.assertEqual(resp_auth_header.status_code, 200)

        # Now query with ?include_pending=true to retrieve unapproved programs
        resp_pending = client.get(
            "/api/v1/programs/?include_pending=true",
            HTTP_X_API_KEY=api_key_obj.key,
        )
        self.assertEqual(resp_pending.status_code, 200)
        pending_titles = [item["title"] for item in resp_pending.json()["results"]]
        self.assertIn("Approved Ingest Program", pending_titles)
        self.assertIn("Unapproved Pending Review Program", pending_titles)
        self.assertIn("Unapproved Draft Program", pending_titles)

        # Specific query for ?status=pending_review
        resp_only_pending = client.get(
            "/api/v1/programs/?status=pending_review",
            HTTP_X_API_KEY=api_key_obj.key,
        )
        self.assertEqual(resp_only_pending.status_code, 200)
        only_pending_titles = [item["title"] for item in resp_only_pending.json()["results"]]
        self.assertEqual(only_pending_titles, ["Unapproved Pending Review Program"])

        # Check API Key last_used_at was updated
        api_key_obj.refresh_from_db()
        self.assertIsNotNone(api_key_obj.last_used_at)

        # Verify Swagger UI endpoint (/api/docs/) and Schema endpoint (/api/schema/)
        resp_swagger = client.get(reverse("api-docs"))
        self.assertEqual(resp_swagger.status_code, 200)
        self.assertIn(b"swagger-ui", resp_swagger.content.lower())

        resp_schema = client.get(reverse("api-schema"))
        self.assertEqual(resp_schema.status_code, 200)

    # 18. API Key Management UI View Tests (Admin Only)
    def test_api_key_ui_view_admin_only_access(self):
        client_creator = Client()
        client_creator.login(username="creator", password="password123")

        # Non-admin user (creator) GET API keys view -> 403 Forbidden
        resp_creator = client_creator.get(reverse("api_keys_view"))
        self.assertEqual(resp_creator.status_code, 403)

        # Non-admin POST create -> 403 Forbidden
        resp_creator_post = client_creator.post(reverse("api_keys_view"), {"name": "Hacker Key"})
        self.assertEqual(resp_creator_post.status_code, 403)

        # Admin user has access
        client_admin = Client()
        client_admin.login(username="admin", password="password123")

        resp_admin = client_admin.get(reverse("api_keys_view"))
        self.assertEqual(resp_admin.status_code, 200)

        # Admin POST create new API key
        post_resp = client_admin.post(reverse("api_keys_view"), {"name": "Test Key UI"})
        self.assertEqual(post_resp.status_code, 200)
        self.assertIn("new_key", post_resp.context)
        key_str = post_resp.context["new_key"]
        self.assertTrue(key_str.startswith("wcgtv_"))

        created_key = APIKey.objects.get(name="Test Key UI")
        self.assertTrue(created_key.is_active)

        # Toggle disable
        toggle_resp = client_admin.post(reverse("api_key_toggle", kwargs={"pk": created_key.pk}))
        self.assertRedirects(toggle_resp, reverse("api_keys_view"))
        created_key.refresh_from_db()
        self.assertFalse(created_key.is_active)

        # Delete key
        del_resp = client_admin.post(reverse("api_key_delete", kwargs={"pk": created_key.pk}))
        self.assertRedirects(del_resp, reverse("api_keys_view"))
        self.assertFalse(APIKey.objects.filter(pk=created_key.pk).exists())
