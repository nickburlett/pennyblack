from django.conf.urls import patterns, url
from django.contrib import admin
try:
    from django.contrib.admin.utils import unquote
except ImportError:
    from django.contrib.admin.util import unquote
from django import forms
from django.core.context_processors import csrf
from django.shortcuts import render_to_response
from django.utils.translation import ugettext_lazy as _
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse

from pennyblack import settings

class JobAdminForm(forms.ModelForm):
    from pennyblack.models.newsletter import Newsletter
    newsletter = forms.ModelChoiceField(queryset=Newsletter.objects.massmail())

class JobAdmin(admin.ModelAdmin):
    from pennyblack.models.link import LinkInline
    from pennyblack.models.mail import MailInline

    date_hierarchy = 'date_deliver_start'
    actions = None
    list_display = ('newsletter', 'group_object', 'status', 'public_slug', 'field_mails_total', 'field_mails_sent', 'date_created')
    list_filter = ('status', 'newsletter',)
    fields = ('newsletter', 'collection', 'status', 'group_object', 'field_mails_total', 'field_mails_sent', 'date_deliver_start', 'date_deliver_finished', 'public_slug', 'utm_campaign')
    readonly_fields = ('collection', 'status', 'group_object', 'field_mails_total', 'field_mails_sent', 'date_deliver_start', 'date_deliver_finished',)
    inlines = (LinkInline, MailInline,)
    raw_id_fields=('newsletter',)
    massmail_form = JobAdminForm

    def get_form(self, request, obj=None, **kwargs):
        if obj and obj.status in settings.JOB_STATUS_CAN_EDIT:
            kwargs['form'] = self.massmail_form
        return super(JobAdmin, self).get_form(request, obj, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in settings.JOB_STATUS_CAN_EDIT:
            return self.readonly_fields
        else:
            return self.readonly_fields + ('newsletter',)

    def change_view(self, request, object_id, extra_context={}):
        obj = self.get_object(request, unquote(object_id))
        extra_context['can_send'] = obj.can_send()
        request._pennyblack_job_obj = obj  # add object to request for the mail inline
        return super(JobAdmin, self).change_view(request, object_id, extra_context=extra_context)

    def send_newsletter_view(self, request, object_id):
        obj = self.get_object(request, unquote(object_id))
        if request.method == 'POST' and "_send" in request.POST:
            obj.start_sending()
            self.message_user(request, _("Newsletter has been marked for delivery."))
        return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.model._meta.app_label, self.model._meta.model_name)))

    def response_change(self, request, obj):
        """
        Determines the HttpResponse for the change_view stage.
        """
        if "_send_prepare" in request.POST:
            context = {
                'object': obj,
                'opts': self.model._meta,
                'app_label': self.model._meta.app_label,
            }
            context.update(csrf(request))
            return render_to_response(
                'admin/pennyblack/job/send_confirmation.html', context)
        return super(JobAdmin, self).response_change(request, obj)

    def get_urls(self):
        urls = super(JobAdmin, self).get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        my_urls = patterns('',
            url(r'^(?P<object_id>\d+)/send/$', self.admin_site.admin_view(self.send_newsletter_view), name=('%s_%s_send' % info)),
        )
        return my_urls + urls

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class JobStatisticAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_deliver_start'
    actions = None
    list_display = ('newsletter', 'group_object', 'field_mails_total', 'field_mails_sent', 'field_opening_rate', 'date_created')
    # list_filter   = ('status', 'newsletter',)
    fields = ('newsletter', 'collection', 'group_object', 'date_deliver_start', 'date_deliver_finished', 'utm_campaign')
    readonly_fields = ('newsletter', 'collection', 'group_object', 'date_deliver_start', 'date_deliver_finished', 'utm_campaign')

    def get_queryset(self, request):
        return self.model.objects.exclude(status=1)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_graph_data(self, obj):
        date_start = obj.date_deliver_start.replace(minute=0, second=0, microsecond=0)
        opened_serie = []
        for i in range(336):
            t = date_start + datetime.timedelta(hours=i)
            count_opened = obj.mails.exclude(viewed=None).filter(viewed__lt=t).count()
            opened_serie.append('[%s000,%s]' % (t.strftime('%s'), count_opened))
            if t > now():
                break
        return {
            'opened_serie': ','.join(opened_serie),
        }

    def change_view(self, request, object_id, extra_context={}):
        obj = self.get_object(request, unquote(object_id))
        graph_data = self.get_graph_data(obj)
        extra_context.update(graph_data)
        return super(JobStatisticAdmin, self).change_view(request, object_id, extra_context=extra_context)

    def email_list_view(self, request, object_id):
        obj = self.get_object(request, unquote(object_id))
        context = {
            'object': obj,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
        }

        return render_to_response('admin/pennyblack/jobstatistic/email_list.html', context)

    def user_agents_view(self, request, object_id):
        from pennyblack.models import EmailClient
        obj = self.get_object(request, unquote(object_id))
        user_agents = EmailClient.objects.filter(mail__job__id=obj.id).values('user_agent').annotate(count=models.Count('user_agent')).order_by('-count')
        context = {
            'object': obj,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'user_agents': user_agents
        }

        return render_to_response('admin/pennyblack/jobstatistic/user_agents.html', context)

    def get_urls(self):
        urls = super(JobStatisticAdmin, self).get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        my_urls = patterns('',
            url(r'^(?P<object_id>\d+)/email-list/$', self.admin_site.admin_view(self.email_list_view), name='%s_%s_email_list' % info),
            url(r'^(?P<object_id>\d+)/user-agents/$', self.admin_site.admin_view(self.user_agents_view), name='%s_%s_user_agents' % info),
        )
        return my_urls + urls
