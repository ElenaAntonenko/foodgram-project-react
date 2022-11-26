import django_filters
from django_filters import rest_framework
from django_filters.rest_framework import FilterSet
from recipes.models import Ingredient, Recipe, Tag


class IngredientFilter(FilterSet):
    """Поиск по названию ингредиента."""

    name = rest_framework.CharFilter(lookup_expr='istartswith')

    class Meta:
        model = Ingredient
        fields = ('name', )


class RecipeFilter(django_filters.FilterSet):
    """ Отображение избранного и списка покупок"""

    tags = django_filters.filters.ModelMultipleChoiceFilter(
        queryset=Tag.objects.all(),
        field_name='tags__slug',
        to_field_name='slug')
    is_favorited = django_filters.filters.NumberFilter(
        method='is_recipe_in_favorites_filter')
    is_in_shopping_cart = django_filters.filters.NumberFilter(
        method='is_recipe_in_shoppingcart_filter')

    def is_recipe_in_favorites_filter(self, queryset, name, value):
        if self.request.user.is_authenticated:
            if self.data.get('is_favorited') == '1':
                return self.queryset.filter(
                    favorites__user=self.request.user
                )
            else:
                return self.queryset.exclude(
                    favorites__user=self.request.user
                )
        return self.queryset

    def get_is_in_shopping_cart(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            if self.data.get('is_in_shopping_cart') == '1':
                return self.queryset.filter(
                    shopping_recipe__user=self.request.user
                )
            else:
                return self.queryset.exclude(
                    shopping_recipe__user=self.request.user
                )
        return self.queryset

    class Meta:
        model = Recipe
        fields = ('tags', 'author', 'is_favorited', 'is_in_shopping_cart')
