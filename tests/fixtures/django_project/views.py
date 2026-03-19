from django.http import JsonResponse
from django.views import View


def author_list(request):
    return JsonResponse({"authors": []})


def author_detail(request, pk):
    return JsonResponse({"id": pk})


class BookListView(View):
    def get(self, request):
        return JsonResponse({"books": []})
