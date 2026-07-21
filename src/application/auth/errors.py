class InvalidCredentialsError(Exception):
	# Generic message on purpose — identical for unknown-user and wrong-password so
	# the response can't be used to enumerate accounts. The 401 status is decided
	# by the global exception handler, not carried on the exception.
	def __init__(self, message: str = "Invalid username or password"):
		super().__init__(message)
		self.message = message
