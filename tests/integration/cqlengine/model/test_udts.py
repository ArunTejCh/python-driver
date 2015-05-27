# Copyright 2015 DataStax, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime, date, time
from decimal import Decimal
import unittest
from uuid import UUID, uuid4

from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns
from cassandra.cqlengine.management import sync_table, sync_type, create_keyspace_simple, drop_keyspace
from cassandra.util import Date, Time

from tests.integration import get_server_versions, PROTOCOL_VERSION
from tests.integration.cqlengine.base import BaseCassEngTestCase


class UserDefinedTypeTests(BaseCassEngTestCase):

    @classmethod
    def setUpClass(self):
        if PROTOCOL_VERSION < 3:
            raise unittest.SkipTest("UDTs require native protocol 3+, currently using: {0}".format(PROTOCOL_VERSION))

    def test_can_create_udts(self):
        class User(UserType):
            age = columns.Integer()
            name = columns.Text()

        sync_type("cqlengine_test", User)
        user = User(age=42, name="John")
        self.assertEqual(42, user.age)
        self.assertEqual("John", user.name)

        # Add a field
        class User(UserType):
            age = columns.Integer()
            name = columns.Text()
            gender = columns.Text()

        sync_type("cqlengine_test", User)
        user = User(age=42, name="John", gender="male")
        self.assertEqual(42, user.age)
        self.assertEqual("John", user.name)
        self.assertEqual("male", user.gender)

        # Remove a field
        class User(UserType):
            age = columns.Integer()
            name = columns.Text()

        sync_type("cqlengine_test", User)
        user = User(age=42, name="John", gender="male")
        with self.assertRaises(AttributeError):
            user.gender

    def test_can_insert_udts(self):
        class User(UserType):
            age = columns.Integer()
            name = columns.Text()

        class UserModel(Model):
            id = columns.Integer(primary_key=True)
            info = columns.UserDefinedType(User)

        sync_table(UserModel)

        user = User(age=42, name="John")
        UserModel.create(id=0, info=user)

        self.assertEqual(1, UserModel.objects.count())

        john = UserModel.objects().first()
        self.assertEqual(0, john.id)
        self.assertTrue(type(john.info) is User)
        self.assertEqual(42, john.info.age)
        self.assertEqual("John", john.info.name)

    def test_can_update_udts(self):
        class User(UserType):
            age = columns.Integer()
            name = columns.Text()

        class UserModel(Model):
            id = columns.Integer(primary_key=True)
            info = columns.UserDefinedType(User)

        sync_table(UserModel)

        user = User(age=42, name="John")
        created_user = UserModel.create(id=0, info=user)

        john_info = UserModel.objects().first().info
        self.assertEqual(42, john_info.age)
        self.assertEqual("John", john_info.name)

        created_user.info = User(age=22, name="Mary")
        created_user.save()

        mary_info = UserModel.objects().first().info
        self.assertEqual(22, mary_info.age)
        self.assertEqual("Mary", mary_info.name)

    def test_can_create_same_udt_different_keyspaces(self):
        class User(UserType):
            age = columns.Integer()
            name = columns.Text()

        sync_type("cqlengine_test", User)

        create_keyspace_simple("simplex", 1)
        sync_type("simplex", User)
        drop_keyspace("simplex")

    def test_can_insert_partial_udts(self):
        class User(UserType):
            age = columns.Integer()
            name = columns.Text()
            gender = columns.Text()

        class UserModel(Model):
            id = columns.Integer(primary_key=True)
            info = columns.UserDefinedType(User)

        sync_table(UserModel)

        user = User(age=42, name="John")
        UserModel.create(id=0, info=user)

        john_info = UserModel.objects().first().info
        self.assertEqual(42, john_info.age)
        self.assertEqual("John", john_info.name)
        self.assertIsNone(john_info.gender)

        user = User(age=42)
        UserModel.create(id=0, info=user)

        john_info = UserModel.objects().first().info
        self.assertEqual(42, john_info.age)
        self.assertIsNone(john_info.name)
        self.assertIsNone(john_info.gender)

    def test_can_insert_nested_udts(self):
        class Depth_0(UserType):
            age = columns.Integer()
            name = columns.Text()

        class Depth_1(UserType):
            value = columns.UserDefinedType(Depth_0)

        class Depth_2(UserType):
            value = columns.UserDefinedType(Depth_1)

        class Depth_3(UserType):
            value = columns.UserDefinedType(Depth_2)

        class DepthModel(Model):
            id = columns.Integer(primary_key=True)
            v_0 = columns.UserDefinedType(Depth_0)
            v_1 = columns.UserDefinedType(Depth_1)
            v_2 = columns.UserDefinedType(Depth_2)
            v_3 = columns.UserDefinedType(Depth_3)

        sync_table(DepthModel)

        udts = [Depth_0(age=42, name="John")]
        udts.append(Depth_1(value=udts[0]))
        udts.append(Depth_2(value=udts[1]))
        udts.append(Depth_3(value=udts[2]))

        DepthModel.create(id=0, v_0=udts[0], v_1=udts[1], v_2=udts[2], v_3=udts[3])
        output = DepthModel.objects().first()

        self.assertEqual(udts[0], output.v_0)
        self.assertEqual(udts[1], output.v_1)
        self.assertEqual(udts[2], output.v_2)
        self.assertEqual(udts[3], output.v_3)

    def test_can_insert_udts_with_nones(self):
        """
        Test for inserting all column types as empty into a UserType as None's

        test_can_insert_udts_with_nones tests that each cqlengine column type can be inserted into a UserType as None's.
        It first creates a UserType that has each cqlengine column type, and a corresponding table/Model. It then creates
        a UserType instance where all the fields are None's and inserts the UserType as an instance of the Model. Finally,
        it verifies that each column read from the UserType from Cassandra is None.

        @since 2.5.0
        @jira_ticket PYTHON-251
        @expected_result The UserType is inserted with each column type, and the resulting read yields None's for each column.

        @test_category data_types:udt
        """

        class AllDatatypes(UserType):
            a = columns.Ascii()
            b = columns.BigInt()
            c = columns.Blob()
            d = columns.Boolean()
            e = columns.DateTime()
            f = columns.Decimal()
            g = columns.Double()
            h = columns.Float(double_precision=False)
            i = columns.Inet()
            j = columns.Integer()
            k = columns.Text()
            l = columns.TimeUUID()
            m = columns.UUID()
            n = columns.VarInt()

        class AllDatatypesModel(Model):
            id = columns.Integer(primary_key=True)
            data = columns.UserDefinedType(AllDatatypes)

        sync_table(AllDatatypesModel)

        input = AllDatatypes(a=None, b=None, c=None, d=None, e=None, f=None, g=None, h=None, i=None, j=None, k=None,
                             l=None, m=None, n=None)
        AllDatatypesModel.create(id=0, data=input)

        self.assertEqual(1, AllDatatypesModel.objects.count())

        output = AllDatatypesModel.objects().first().data
        self.assertEqual(input, output)

    def test_can_insert_udts_with_all_datatypes(self):
        """
        Test for inserting all column types into a UserType

        test_can_insert_udts_with_all_datatypes tests that each cqlengine column type can be inserted into a UserType.
        It first creates a UserType that has each cqlengine column type, and a corresponding table/Model. It then creates
        a UserType instance where all the fields have corresponding data, and inserts the UserType as an instance of the Model.
        Finally, it verifies that each column read from the UserType from Cassandra is the same as the input parameters.

        @since 2.5.0
        @jira_ticket PYTHON-251
        @expected_result The UserType is inserted with each column type, and the resulting read yields proper data for each column.

        @test_category data_types:udt
        """

        class AllDatatypes(UserType):
            a = columns.Ascii()
            b = columns.BigInt()
            c = columns.Blob()
            d = columns.Boolean()
            e = columns.DateTime()
            f = columns.Decimal()
            g = columns.Double()
            h = columns.Float(double_precision=False)
            i = columns.Inet()
            j = columns.Integer()
            k = columns.Text()
            l = columns.TimeUUID()
            m = columns.UUID()
            n = columns.VarInt()

        class AllDatatypesModel(Model):
            id = columns.Integer(primary_key=True)
            data = columns.UserDefinedType(AllDatatypes)

        sync_table(AllDatatypesModel)

        input = AllDatatypes(a='ascii', b=2 ** 63 - 1, c=bytearray(b'hello world'), d=True,
                             e=datetime.utcfromtimestamp(872835240), f=Decimal('12.3E+7'), g=2.39,
                             h=3.4028234663852886e+38, i='123.123.123.123', j=2147483647, k='text',
                             l=UUID('FE2B4360-28C6-11E2-81C1-0800200C9A66'),
                             m=UUID('067e6162-3b6f-4ae2-a171-2470b63dff00'), n=int(str(2147483647) + '000'))
        AllDatatypesModel.create(id=0, data=input)

        self.assertEqual(1, AllDatatypesModel.objects.count())
        output = AllDatatypesModel.objects().first().data

        for i in range(ord('a'), ord('a') + 14):
            self.assertEqual(input[chr(i)], output[chr(i)])

    def test_can_insert_udts_protocol_v4_datatypes(self):
        """
        Test for inserting all protocol v4 column types into a UserType

        test_can_insert_udts_protocol_v4_datatypes tests that each protocol v4 cqlengine column type can be inserted
        into a UserType. It first creates a UserType that has each protocol v4 cqlengine column type, and a corresponding
        table/Model. It then creates a UserType instance where all the fields have corresponding data, and inserts the
        UserType as an instance of the Model. Finally, it verifies that each column read from the UserType from Cassandra
        is the same as the input parameters.

        @since 2.6.0
        @jira_ticket PYTHON-245
        @expected_result The UserType is inserted with each protocol v4 column type, and the resulting read yields proper data for each column.

        @test_category data_types:udt
        """

        if PROTOCOL_VERSION < 4:
            raise unittest.SkipTest("Protocol v4 datatypes in UDTs require native protocol 4+, currently using: {0}".format(PROTOCOL_VERSION))

        class AllDatatypes(UserType):
            a = columns.Date()
            b = columns.SmallInt()
            c = columns.Time()
            d = columns.TinyInt()

        class AllDatatypesModel(Model):
            id = columns.Integer(primary_key=True)
            data = columns.UserDefinedType(AllDatatypes)

        sync_table(AllDatatypesModel)

        input = AllDatatypes(a=Date(date(1970, 1, 1)), b=32523, c=Time(time(16, 47, 25, 7)), d=123)
        AllDatatypesModel.create(id=0, data=input)

        self.assertEqual(1, AllDatatypesModel.objects.count())
        output = AllDatatypesModel.objects().first().data

        for i in range(ord('a'), ord('a') + 3):
            self.assertEqual(input[chr(i)], output[chr(i)])

    def test_nested_udts_inserts(self):
        """
        Test for inserting collections of user types using cql engine.

        test_nested_udts_inserts Constructs a model that contains a list of usertypes. It will then attempt to insert
        them. The expectation is that no exception is thrown during insert. For sanity sake we also validate that our
        input and output values match. This combination of model, and UT produces a syntax error in 2.5.1 due to
        improper quoting around the names collection.

        @since 2.6.0
        @jira_ticket PYTHON-311
        @expected_result No syntax exception thrown

        @test_category data_types:udt
        """

        class Name(UserType):
            type_name__ = "header"

            name = columns.Text()
            value = columns.Text()

        class Container(Model):
            id = columns.UUID(primary_key=True, default=uuid4)
            names = columns.List(columns.UserDefinedType(Name))

        # Construct the objects and insert them
        names = []
        for i in range(0, 10):
            names.append(Name(name="name{0}".format(i), value="value{0}".format(i)))

        # Create table, insert data
        sync_table(Container)
        Container.create(id=UUID('FE2B4360-28C6-11E2-81C1-0800200C9A66'), names=names)

        # Validate input and output matches
        self.assertEqual(1, Container.objects.count())
        names_output = Container.objects().first().names
        self.assertEqual(names_output, names)
