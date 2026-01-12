from django.shortcuts import render

# Create your views here.
# core/views.py

from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from core.api.responses import ok
# Make sure to import the serializer we just made
from core.serializers import UserListSerializer 

User = get_user_model()

class UserListAPI(APIView):
    """
    Returns a list of all users in the system.
    """
    # Security: Only authenticated users can see this. 
    # Change to [IsAdminUser] if you want to restrict it further.
    permission_classes = [IsAuthenticated] 

    @extend_schema(
        responses=UserListSerializer(many=True),
        summary="List all users",
        description="Retrieve a list of all registered users. Useful for assignment dropdowns."
    )
    def get(self, request):
        # Operational Check: You might want to filter only active users for dropdowns
        # users = User.objects.filter(is_active=True)
        users = User.objects.all().order_by("username")
        
        data = UserListSerializer(users, many=True).data
        return ok(data)