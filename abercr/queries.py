LOGIN_QUERY = """
mutation LOGIN_MUTATION(
  $email: String!,
  $password: String!,
  $keepMeSignedIn: Boolean,
  $isLoyaltyConversionTermsAccepted: Boolean,
  $doMergeBag: Boolean,
  $fastEnrollCampaignId: String
) {
  login(
    email: $email
    password: $password
    keepMeSignedIn: $keepMeSignedIn
    isLoyaltyConversionTermsAccepted: $isLoyaltyConversionTermsAccepted
    doMergeBag: $doMergeBag
    fastEnrollCampaignId: $fastEnrollCampaignId
  ) {
    success
    userId
    isPasswordUpdateRequired
    mfaRequiredForAssociates
    errors { ...error __typename }
    __typename
  }
}
fragment error on Error {
  message { key value __typename }
  status
  __typename
}
""".strip()

CREATE_USER_QUERY = """
mutation CREATE_USER_MUTATION(
  $email: String!,
  $password: String!,
  $keepMeSignedIn: Boolean,
  $firstName: String!,
  $lastName: String!,
  $primaryPhone: String,
  $emailOptions: [BrandSelection],
  $ageAboveOrBelow: Boolean,
  $referralCode: String,
  $fastEnrollCampaignId: String,
  $preference: UserPreferencesInput,
  $legalAccept: Boolean
) {
  createUser(
    email: $email
    password: $password
    keepMeSignedIn: $keepMeSignedIn
    firstName: $firstName
    lastName: $lastName
    primaryPhone: $primaryPhone
    emailOptions: $emailOptions
    ageAboveOrBelow: $ageAboveOrBelow
    referralCode: $referralCode
    fastEnrollCampaignId: $fastEnrollCampaignId
    preference: $preference
    legalAccept: $legalAccept
  ) {
    success
    response
    errors { ...error __typename }
    __typename
  }
}
fragment error on Error {
  message { key value __typename }
  status
  __typename
}
""".strip()
