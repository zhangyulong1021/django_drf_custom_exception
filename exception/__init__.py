from rest_framework.exceptions import APIException


class CustomException(APIException):
    pass

# demo
class CourtesyCarException:
    # model
    class Customer:
        # exception
        class AlreadyExists(CustomException):
            status_code = 400
            default_detail = "该客户已存在，并且在保时间重叠"
            default_code = "courtesy_car.customer.already_exists"

        class InvalidEffectiveDate(CustomException):
            status_code = 400
            default_detail = "添加客户时使用了错误的起保日期。比如格式错误或超过90天"
            default_code = "courtesy_car.customer.invalid_effective_date"